//! Shared semantic dispatch, independent of an MCP connection's lifetime.
use super::composition::CompositionResolution;
use super::registry::{GitProvenance, ProcessorDefinition, ProcessorRegistry};
use super::{AgentProgram, Backend, Operation};
use serde_json::{json, Value};
use std::collections::BTreeMap;

fn tools() -> Value {
    json!([
        {"name":"lemmalog_install_rules","description":"Compile and atomically replace this session's typed positive rule program; replay retained facts. Unsupported syntax is rejected.","inputSchema":{"type":"object","properties":{"rules":{"type":"string"},"schemas":{"type":"object","additionalProperties":{"type":"object","properties":{"input":{"type":"boolean"},"fields":{"type":"array","items":{"enum":["int","string"]},"minItems":1}},"required":["input","fields"],"additionalProperties":false}}},"required":["rules","schemas"],"additionalProperties":false}},
        {"name":"apply_changes","description":"Transactionally insert or delete input facts with set semantics.","inputSchema":{"type":"object","properties":{"changes":{"type":"array","items":{"type":"object","properties":{"op":{"enum":["insert","delete"]},"predicate":{"type":"string"},"values":{"type":"array","items":{"type":["integer","string"]}}},"required":["op","predicate","values"],"additionalProperties":false}}},"required":["changes"],"additionalProperties":false}},
        {"name":"lemmalog_query","description":"Dump a declared output relation at the last completed transaction. Returns DDlog row text.","inputSchema":{"type":"object","properties":{"predicate":{"type":"string"}},"required":["predicate"],"additionalProperties":false}},
        {"name":"lemmalog_why","description":"Read direct variable-binding witnesses for a zero-based rule index. Not recursive provenance.","inputSchema":{"type":"object","properties":{"rule":{"type":"integer","minimum":0}},"required":["rule"],"additionalProperties":false}}
    ])
}
fn agent_tools() -> Value {
    fn tool(name: &str, description: &str, properties: Value, required: Value) -> Value {
        json!({"name":name,"description":description,"inputSchema":{"type":"object","properties":properties,"required":required,"additionalProperties":false}})
    }
    json!([
        tool("agent_operations","Discover operator-registered operations. Each takes and returns a string; providers execute outside DDlog.",json!({}),json!([])),
        tool("install_agent_program","Select a registered operation. Author rules consuming agent_result(entity:string, revision:int, output:string). The runtime generates private request/response relations and freshness joins.",json!({"operation":{"type":"string"},"rules":{"type":"string"},"schemas":{"type":"object"}}),json!(["operation","rules","schemas"])),
        tool("submit_agent_input","Submit a versioned input; identity includes operation version, entity, revision and exact payload. Same revision cannot change payload.",json!({"entity":{"type":"string"},"revision":{"type":"integer","minimum":0},"payload":{"type":"string"}}),json!(["entity","revision","payload"])),
        tool("claim_agent_request","Admit external work once per session. Stale or already claimed requests are rejected. No automatic replay after uncertain outcomes.",json!({"request_id":{"type":"string"}}),json!(["request_id"])),
        tool("complete_agent_request","Record the external worker's response. Stale replies are retained but never join current outputs; conflicting responses are rejected.",json!({"request_id":{"type":"string"},"output":{"type":"string"}}),json!(["request_id","output"])),
        tool("agent_request_status","Inspect per-request identity, status and freshness. State is session-local, not durable.",json!({}),json!([]))
    ])
}

/// The indivisible semantic owner. Only transport code controls its lifetime.
pub struct ProgramInstance {
    pub(super) backend: Backend,
    operations: BTreeMap<String, Operation>,
    agent: Option<AgentProgram>,
    registry: Option<ProcessorRegistry>,
    instance_id: Option<String>,
    processor: Option<Value>,
    interface: Option<PublicInterface>,
    composition: Option<CompositionResolution>,
}

impl ProgramInstance {
    pub fn new(
        backend: Backend,
        operations: BTreeMap<String, Operation>,
        registry: Option<ProcessorRegistry>,
        instance_id: Option<String>,
    ) -> Self {
        Self {
            backend,
            operations,
            registry,
            instance_id,
            agent: None,
            processor: None,
            interface: None,
            composition: None,
        }
    }

    pub fn handle_line(&mut self, line: &str) -> Option<Value> {
        match serde_json::from_str::<Value>(line) {
            Ok(message) => self.handle(message),
            Err(_) => Some(rpc_error(Value::Null, -32700, "Invalid JSON")),
        }
    }

    fn handle(&mut self, message: Value) -> Option<Value> {
        if !message.is_object() || message["jsonrpc"] != "2.0" || !message["method"].is_string() {
            return Some(rpc_error(Value::Null, -32600, "Invalid JSON-RPC request"));
        }
        let id = message.get("id")?.clone(); // Notifications do not have replies.
        if !id.is_string() && !id.is_i64() && !id.is_u64() {
            return Some(rpc_error(Value::Null, -32600, "Invalid request ID"));
        }
        let result = match message["method"].as_str().unwrap() {
            "initialize" => {
                json!({"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"lemmalog-ddlog","version":"0.2.0"}})
            }
            "ping" => json!({}),
            "tools/list" => {
                let mut list = tools();
                if !self.operations.is_empty() {
                    list.as_array_mut()
                        .unwrap()
                        .extend(agent_tools().as_array().unwrap().iter().cloned());
                }
                if self.instance_id.is_some() {
                    list.as_array_mut().unwrap().push(json!({"name":"instance_info","description":"Inspect this shared in-memory instance and its pinned processor; no recovery or replay.","inputSchema":{"type":"object","properties":{},"additionalProperties":false}}));
                }
                if self.registry.is_some() {
                    list.as_array_mut()
                        .unwrap()
                        .extend(registry_tools().as_array().unwrap().iter().cloned());
                }
                json!({"tools":list})
            }
            "tools/call" => {
                let name = message["params"]["name"].as_str().unwrap_or("");
                let args = &message["params"]["arguments"];
                match self.call(name, args) {
                    Ok(value) => {
                        json!({"content":[{"type":"text","text":value.to_string()}],"isError":false})
                    }
                    Err(error) => {
                        json!({"content":[{"type":"text","text":actionable_error(name, &error)}],"isError":true})
                    }
                }
            }
            _ => return Some(rpc_error(id, -32601, "Unknown method")),
        };
        Some(json!({"jsonrpc":"2.0","id":id,"result":result}))
    }

    fn call(&mut self, name: &str, a: &Value) -> Result<Value, String> {
        if name == "instance_info" && self.instance_id.is_some() {
            return Ok(
                json!({"instance_id":self.instance_id,"health":self.backend.health(),"processor":self.processor,"composition":self.composition}),
            );
        }
        if name.starts_with("processor_") && name != "processor_install" {
            let registry = self
                .registry
                .as_ref()
                .ok_or("Processor registry is not configured")?;
            if name == "processor_list" || name == "processor_search" {
                let limit = a
                    .get("limit")
                    .map(|value| value.as_u64().ok_or("limit must be an integer"))
                    .transpose()?
                    .unwrap_or(20);
                let limit = usize::try_from(limit).map_err(|e| e.to_string())?;
                let after = a.get("after").map(|_| string(a, "after")).transpose()?;
                let include_archived = a
                    .get("include_archived")
                    .map(|value| value.as_bool().ok_or("include_archived must be a boolean"))
                    .transpose()?
                    .unwrap_or(false);
                let page = if name == "processor_search" {
                    registry.search(string(a, "query")?, limit, after, include_archived)?
                } else {
                    registry.list(limit, after, include_archived)?
                };
                return serde_json::to_value(page).map_err(|e| e.to_string());
            }
            if name == "processor_archive" || name == "processor_restore" {
                let expected_revision = a["expected_revision"]
                    .as_u64()
                    .ok_or("Missing nonnegative expected_revision")?;
                let lifecycle = if name == "processor_archive" {
                    registry.archive(
                        string(a, "processor_id")?,
                        string(a, "expected_version")?,
                        expected_revision,
                    )?
                } else {
                    registry.restore(
                        string(a, "processor_id")?,
                        string(a, "expected_version")?,
                        expected_revision,
                    )?
                };
                return serde_json::to_value(lifecycle).map_err(|e| e.to_string());
            }
            let provenance = || -> Result<Option<GitProvenance>, String> {
                a.get("git_provenance")
                    .filter(|v| !v.is_null())
                    .map(|v| serde_json::from_value(v.clone()).map_err(|e| e.to_string()))
                    .transpose()
            };
            let definition = || -> Result<ProcessorDefinition, String> {
                // Select the shape before deserialization so missing/unknown
                // fields remain visible instead of an opaque untagged-enum error.
                if a["definition"].get("composition").is_some() {
                    serde_json::from_value(a["definition"].clone())
                        .map(ProcessorDefinition::Composition)
                        .map_err(|e| e.to_string())
                } else {
                    serde_json::from_value(a["definition"].clone())
                        .map(ProcessorDefinition::Program)
                        .map_err(|e| e.to_string())
                }
            };
            let record = match name {
                "processor_create" => registry.create(definition()?, provenance()?)?,
                "processor_publish" => registry.publish(
                    string(a, "processor_id")?,
                    definition()?,
                    string(a, "expected_version")?,
                    provenance()?,
                )?,
                "processor_fork" => registry.fork(
                    string(a, "processor_id")?,
                    string(a, "version")?,
                    provenance()?,
                )?,
                "processor_get" => registry.get(
                    string(a, "processor_id")?,
                    a.get("version").map(|_| string(a, "version")).transpose()?,
                )?,
                _ => return Err("Unknown tool".into()),
            };
            return serde_json::to_value(record).map_err(|e| e.to_string());
        }
        if self.instance_id.is_some()
            && self.backend.health() == "failed"
            && name != "agent_request_status"
            && name != "agent_operations"
        {
            return Err("Instance runtime failed; reconcile uncertain work and explicitly create a new instance. Reconnect does not recover state.".into());
        }
        if self.processor.is_some()
            && matches!(
                name,
                "processor_install" | "lemmalog_install_rules" | "install_agent_program"
            )
        {
            return Err("Instance is pinned to an immutable processor version; create a new instance to select another version".into());
        }
        match name {
            "processor_install" => {
                if self.backend.health() != "uninitialized" || self.agent.is_some() {
                    return Err("Select a processor only in a fresh instance".into());
                }
                self.registry
                    .as_ref()
                    .ok_or("Processor registry is not configured")?
                    .ensure_active(string(a, "processor_id")?)?;
                let record = self
                    .registry
                    .as_ref()
                    .ok_or("Processor registry is not configured")?
                    .get(
                        string(a, "processor_id")?,
                        a.get("version").map(|_| string(a, "version")).transpose()?,
                    )?;
                let mut result = match record.definition {
                    ProcessorDefinition::Composition(definition) => {
                        let compiled = self
                            .registry
                            .as_ref()
                            .unwrap()
                            .compile_composition(&definition.composition)?;
                        let result = self
                            .backend
                            .install_source(compiled.source, compiled.schemas)?;
                        self.interface = Some(PublicInterface {
                            inputs: compiled.resolution.inputs.clone(),
                            outputs: compiled.resolution.outputs.clone(),
                        });
                        self.composition = Some(compiled.resolution);
                        result
                    }
                    ProcessorDefinition::Program(definition) => {
                        let result = if let Some(binding) = definition.operation {
                            let operation = self
                                .operations
                                .get(&binding.name)
                                .ok_or("Pinned operation is not registered on this host")?
                                .clone();
                            if operation.version != binding.version
                                || operation.description != binding.description
                            {
                                return Err(
                                    "Pinned operation definition does not match this host registry"
                                        .into(),
                                );
                            }
                            let (agent, result) = AgentProgram::install(
                                &mut self.backend,
                                &binding.name,
                                operation,
                                &definition.rules,
                                definition.schemas,
                            )?;
                            self.agent = Some(agent);
                            result
                        } else {
                            self.backend
                                .install(&definition.rules, definition.schemas)?
                        };
                        self.interface = definition.interface.map(|interface| PublicInterface {
                            inputs: interface
                                .inputs
                                .into_iter()
                                .map(|name| (name.clone(), name))
                                .collect(),
                            outputs: interface
                                .outputs
                                .into_iter()
                                .map(|name| (name.clone(), name))
                                .collect(),
                        });
                        result
                    }
                };
                self.processor =
                    Some(json!({"processor_id":record.processor_id,"version":record.version}));
                result["processor"] = self.processor.clone().unwrap();
                if let Some(composition) = &self.composition {
                    result["composition"] =
                        serde_json::to_value(composition).map_err(|e| e.to_string())?;
                }
                Ok(result)
            }
            "agent_operations" => Ok(
                json!({"operations":self.operations.iter().map(|(name,op)|json!({"name":name,"version":op.version,"description":op.description,"input":"string","output":"string"})).collect::<Vec<_>>()}),
            ),
            "install_agent_program" => {
                let name = string(a, "operation")?;
                let operation = self
                    .operations
                    .get(name)
                    .ok_or("Operation is not registered")?
                    .clone();
                let (agent, result) = AgentProgram::install(
                    &mut self.backend,
                    name,
                    operation,
                    string(a, "rules")?,
                    a["schemas"].clone(),
                )?;
                self.agent = Some(agent);
                Ok(result)
            }
            "submit_agent_input" => self
                .agent
                .as_mut()
                .ok_or("Install an agent program")?
                .submit(
                    &mut self.backend,
                    string(a, "entity")?,
                    a["revision"].as_i64().ok_or("Missing revision")?,
                    string(a, "payload")?,
                ),
            "claim_agent_request" => self
                .agent
                .as_mut()
                .ok_or("Install an agent program")?
                .claim(&mut self.backend, string(a, "request_id")?),
            "complete_agent_request" => self
                .agent
                .as_mut()
                .ok_or("Install an agent program")?
                .complete(
                    &mut self.backend,
                    string(a, "request_id")?,
                    string(a, "output")?,
                ),
            "agent_request_status" => self
                .agent
                .as_ref()
                .map(AgentProgram::status)
                .ok_or("Install an agent program".into()),
            "lemmalog_install_rules" if self.agent.is_some() => {
                Err("Create a new instance to replace a registered agent program".into())
            }
            "lemmalog_install_rules" => self
                .backend
                .install(string(a, "rules")?, a["schemas"].clone()),
            "apply_changes" => {
                if self.agent.is_some()
                    && a["changes"].as_array().is_some_and(|changes| {
                        changes.iter().any(|c| {
                            c["predicate"]
                                .as_str()
                                .is_some_and(|p| p.starts_with("agent_"))
                        })
                    })
                {
                    return Err(
                        "Registered operation relations must use the operation tools".into(),
                    );
                }
                if let Some(interface) = &self.interface {
                    let changes = interface.changes(&a["changes"])?;
                    let mut result = self.backend.apply(&changes)?;
                    result["deltas"] =
                        json!(interface.outputs(result["deltas"].as_str().unwrap_or("")));
                    Ok(result)
                } else {
                    self.backend.apply(&a["changes"])
                }
            }
            "lemmalog_query" => {
                let predicate = string(a, "predicate")?;
                if let Some(interface) = &self.interface {
                    let physical = interface
                        .outputs
                        .get(predicate)
                        .ok_or_else(|| format!("Unknown exported output {predicate}"))?;
                    let mut result = self.backend.query(physical)?;
                    result["rows"] =
                        json!(interface.outputs(result["rows"].as_str().unwrap_or("")));
                    Ok(result)
                } else {
                    self.backend.query(predicate)
                }
            }
            "lemmalog_why" => {
                let rule =
                    usize::try_from(a["rule"].as_u64().ok_or("Missing nonnegative rule index")?)
                        .map_err(|e| e.to_string())?;
                let mut result = self.backend.why(rule)?;
                if let Some(composition) = &self.composition {
                    result["origin"] = composition
                        .rules
                        .get(rule)
                        .ok_or("Unknown composition rule index")?
                        .clone();
                }
                Ok(result)
            }
            _ => Err("Unknown tool".into()),
        }
    }
}

/// Only these declared ports can be addressed through the ordinary fact tools.
/// Witnesses deliberately expose direct rule bindings through their separate API.
struct PublicInterface {
    inputs: BTreeMap<String, String>,
    outputs: BTreeMap<String, String>,
}
impl PublicInterface {
    fn changes(&self, changes: &Value) -> Result<Value, String> {
        let mut mapped = changes.as_array().ok_or("Expected changes array")?.clone();
        for change in &mut mapped {
            let predicate = change["predicate"].as_str().ok_or("Missing predicate")?;
            let physical = self
                .inputs
                .get(predicate)
                .ok_or_else(|| format!("Unknown exported input {predicate}"))?;
            change["predicate"] = json!(physical);
        }
        Ok(json!(mapped))
    }
    fn outputs(&self, rows: &str) -> String {
        // DDlog's CLI emits one relation header or row per line; replace only
        // the leading identifier, never a string value containing that name.
        let mut result = String::new();
        for line in rows.lines() {
            for (public, physical) in &self.outputs {
                if let Some(suffix) = line.strip_prefix(&format!("R_{physical}")) {
                    if suffix == ":" || suffix.starts_with('{') {
                        result.push_str(&format!("R_{public}{suffix}\n"));
                        break;
                    }
                }
            }
        }
        result
    }
}

/// Cause/state stays intact; the tool surface supplies a bounded next action.
/// This never turns an uncertain result into authorization to retry a mutation.
fn actionable_error(tool: &str, error: &str) -> String {
    if error.contains("Next action:") {
        return error.to_string();
    }
    let action = if error.contains("Runtime unavailable") || error.contains("uncertain") {
        "Inspect instance_info and reconcile the uncertain operation before deciding whether to create a new instance; do not blindly retry it."
    } else if tool == "processor_archive" || tool == "processor_restore" {
        "Read processor_search with the processor identity and include_archived=true; reconsider the change using its current version and lifecycle_revision before submitting new preconditions."
    } else if error.contains("compilation failed") {
        "Inspect the reported build log for compiler diagnostics; correct the saved definition or operator toolchain, then explicitly install a valid version in a fresh instance."
    } else if error.contains("conflict") || error.contains("conflict:") {
        "Read the latest processor version and reconsider the intended edit before submitting a new conditional publication."
    } else {
        match tool {
            "processor_create" | "processor_publish" => "Correct the reported syntax, schema or connection in definition; use an exported endpoint with matching field types and exactly one source per input. Inspect tools/list for the accepted definition shapes, then submit the corrected definition.",
            "processor_list" | "processor_search" => "Use a limit from 1 through 100 and pass the preceding next_cursor as after with the same query and include_archived option.",
            "processor_get" | "processor_fork" => "Discover the identity with processor_list or processor_search (include_archived=true for history), then read a valid exact version using processor_get.",
            "processor_install" => "Inspect instance_info and processor_get for the intended exact version; select an active definition and install it in a fresh instance.",
            "lemmalog_query" => "Read the pinned definition or composition metadata using processor_get, then query a declared exported output name.",
            "lemmalog_why" => "Read composition.rules from instance_info or processor_get and choose an existing zero-based rule index; ordinary programs use their authored rule order.",
            "apply_changes" => "Correct the input predicate, operation and field values using the declared input schemas before submitting the transaction.",
            _ => "Inspect tools/list for supported tools and required argument shapes, then correct the reported request.",
        }
    };
    format!("{error}\nNext action: {action}")
}

fn string<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
    value[key]
        .as_str()
        .ok_or_else(|| format!("Missing string field: {key}"))
}
pub(super) fn rpc_error(id: Value, code: i64, message: &str) -> Value {
    json!({"jsonrpc":"2.0","id":id,"error":{"code":code,"message":message}})
}

fn registry_tools() -> Value {
    let endpoint = json!({"type":"object","properties":{"node":{"type":"string"},"relation":{"type":"string"}},"required":["node","relation"],"additionalProperties":false});
    let reference = json!({"type":"object","properties":{"processor_id":{"type":"string"},"version":{"type":"string"}},"required":["processor_id","version"],"additionalProperties":false});
    let interface = json!({"type":"object","properties":{"inputs":{"type":"array","items":{"type":"string"}},"outputs":{"type":"array","items":{"type":"string"},"minItems":1}},"required":["inputs","outputs"],"additionalProperties":false});
    let definition = json!({"oneOf":[
        {"type":"object","properties":{"rules":{"type":"string"},"schemas":{"type":"object"},"interface":interface,"operation":{"type":["object","null"],"properties":{"name":{"type":"string"},"version":{"type":"string"},"description":{"type":"string"}},"required":["name","version","description"],"additionalProperties":false}},"required":["rules","schemas"],"additionalProperties":false},
        {"type":"object","properties":{"composition":{"type":"object","properties":{
            "nodes":{"type":"object","minProperties":1,"additionalProperties":reference},
            "inputs":{"type":"object","additionalProperties":{"type":"object","properties":{"fields":{"type":"array","items":{"enum":["int","string"]},"minItems":1},"targets":{"type":"array","items":endpoint,"minItems":1}},"required":["fields","targets"],"additionalProperties":false}},
            "bindings":{"type":"array","items":{"type":"object","properties":{"from":endpoint,"to":endpoint},"required":["from","to"],"additionalProperties":false}},
            "outputs":{"type":"object","minProperties":1,"additionalProperties":endpoint}
        },"required":["nodes","inputs","bindings","outputs"],"additionalProperties":false}},"required":["composition"],"additionalProperties":false}
    ]});
    let tool = |name: &str, description: &str, properties: Value, required: Value| json!({"name":name,"description":description,"inputSchema":{"type":"object","properties":properties,"required":required,"additionalProperties":false}});
    let discovery = json!({"limit":{"type":"integer","minimum":1,"maximum":100,"default":20},"after":{"type":"string"},"include_archived":{"type":"boolean","default":false}});
    let mut search = discovery.clone();
    search["query"] = json!({"type":"string"});
    json!([
        tool("processor_list","List saved processors ordered by stable identity, with bounded keyset pagination. Pass next_cursor as after; concurrent changes do not form a snapshot. Archived entries are omitted unless include_archived is true.",discovery,json!([])),
        tool("processor_search","Case-insensitive literal substring search across identity, version and compact authored definition JSON. Same pagination and archive rules as processor_list; empty query lists all.",search,json!(["query"])),
        tool("processor_archive","Conditionally archive using both the expected code version and lifecycle revision. Retains code/lineage and existing instances/composition references. Same-state at current revision is a no-op; stale revisions conflict.",json!({"processor_id":{"type":"string"},"expected_version":{"type":"string"},"expected_revision":{"type":"integer","minimum":0}}),json!(["processor_id","expected_version","expected_revision"])),
        tool("processor_restore","Conditionally restore an archived identity to active discovery and new use, using its expected code version and lifecycle revision. Preserves versions/pins and does not compile or run. Same-state at current revision is a no-op; stale revisions conflict.",json!({"processor_id":{"type":"string"},"expected_version":{"type":"string"},"expected_revision":{"type":"integer","minimum":0}}),json!(["processor_id","expected_version","expected_revision"])),
        tool("processor_create","Validate and save a program under a new stable identity. Supply rules or a composition manifest referencing exact immutable pure program versions, including other composed programs. Returns resolved dependencies and witness origins. Does not compile or activate a graph.",json!({"definition":definition,"git_provenance":{"type":"object"}}),json!(["definition"])),
        tool("processor_publish","Validate syntax and types, then save a definition and move current only if expected_version matches. Does not activate a graph.",json!({"processor_id":{"type":"string"},"expected_version":{"type":"string"},"definition":definition,"git_provenance":{"type":"object"}}),json!(["processor_id","expected_version","definition"])),
        tool("processor_fork","Create a new processor identity referencing an exact source version as lineage.",json!({"processor_id":{"type":"string"},"version":{"type":"string"},"git_provenance":{"type":"object"}}),json!(["processor_id","version"])),
        tool("processor_get","Read an immutable version; omitted version resolves current once.",json!({"processor_id":{"type":"string"},"version":{"type":"string"}}),json!(["processor_id"])),
        tool("processor_install","Compile, activate and pin a program version in a fresh instance. A composition runs as one graph; current pointer updates cannot change it.",json!({"processor_id":{"type":"string"},"version":{"type":"string"}}),json!(["processor_id"]))
    ])
}

#[cfg(test)]
mod interface_tests {
    use super::*;
    #[test]
    fn interface_filters_private_deltas_without_rewriting_values() {
        let interface = PublicInterface {
            inputs: BTreeMap::from([("source".into(), "Input_source".into())]),
            outputs: BTreeMap::from([("result".into(), "Output_result".into())]),
        };
        let text = "Evidence0:\nEvidence0{.v_X = 1}: +1\nR_Module0_private:\nR_Module0_private{.f0 = 1}: +1\nR_Output_result:\nR_Output_result{.f0 = \"R_Output_result\"}: +1\nR_Output_result_other{.f0 = 2}: +1\n";
        assert_eq!(
            interface.outputs(text),
            "R_result:\nR_result{.f0 = \"R_Output_result\"}: +1\n"
        );
        assert!(interface
            .changes(&json!([{"predicate":"Input_source","values":[1],"op":"insert"}]))
            .is_err());
        assert_eq!(
            interface
                .changes(&json!([{"predicate":"source","values":[1],"op":"insert"}]))
                .unwrap(),
            json!([{"predicate":"Input_source","values":[1],"op":"insert"}])
        );
    }
}

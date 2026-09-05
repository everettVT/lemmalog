//! Experimental MCP surface using the real DDlog backend.
use lemmalog::ddlog::{AgentProgram, Backend, Operation};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::io::{BufRead, Write};

fn tools() -> Value {
    json!([
        {"name":"lemmalog_install_rules","description":"Compile and atomically replace this session's typed positive rule program; replay retained facts. Unsupported syntax is rejected.","inputSchema":{"type":"object","properties":{"rules":{"type":"string"},"schemas":{"type":"object","additionalProperties":{"type":"object","properties":{"input":{"type":"boolean"},"fields":{"type":"array","items":{"enum":["int","string"]},"minItems":1}},"required":["input","fields"],"additionalProperties":false}}},"required":["rules","schemas"],"additionalProperties":false}},
        {"name":"apply_changes","description":"Transactionally insert or delete input facts with set semantics.","inputSchema":{"type":"object","properties":{"changes":{"type":"array","items":{"type":"object","properties":{"op":{"enum":["insert","delete"]},"predicate":{"type":"string"},"values":{"type":"array","items":{"type":["integer","string"]}}},"required":["op","predicate","values"],"additionalProperties":false}}},"required":["changes"],"additionalProperties":false}},
        {"name":"lemmalog_query","description":"Dump a declared output relation at the last completed transaction. Returns DDlog row text.","inputSchema":{"type":"object","properties":{"predicate":{"type":"string"}},"required":["predicate"],"additionalProperties":false}},
        {"name":"lemmalog_why","description":"Read direct variable-binding witnesses for a zero-based rule index. Not recursive provenance.","inputSchema":{"type":"object","properties":{"rule":{"type":"integer","minimum":0}},"required":["rule"],"additionalProperties":false}}
    ])
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = std::env::var("LEMMALOG_DDLOG_WORKDIR")?;
    let driver = std::env::var("LEMMALOG_DDLOG_BUILD")?;
    // A fresh session directory avoids collisions with other servers and prior builds.
    let root = std::path::PathBuf::from(root).join(format!(
        "session-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos()
    ));
    let mut backend = Backend::new(root, driver.into());
    let registry: BTreeMap<String, Operation> = match std::env::var("LEMMALOG_AGENT_OPERATIONS") {
        Ok(path) => serde_json::from_str(&std::fs::read_to_string(path)?)?,
        Err(_) => BTreeMap::new(),
    };
    let mut agent: Option<AgentProgram> = None;
    let mut stdout = std::io::stdout().lock();
    for line in std::io::stdin().lock().lines() {
        let msg: Value = match serde_json::from_str(&line?) {
            Ok(v) => v,
            Err(_) => continue,
        };
        let Some(id) = msg.get("id") else { continue };
        let result = match msg["method"].as_str() {
            Some("initialize") => {
                json!({"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"lemmalog-ddlog","version":"0.1.0"}})
            }
            Some("tools/list") => {
                let mut list = tools();
                if !registry.is_empty() {
                    list.as_array_mut()
                        .unwrap()
                        .extend(agent_tools().as_array().unwrap().iter().cloned());
                }
                json!({"tools":list})
            }
            Some("tools/call") => {
                let a = &msg["params"]["arguments"];
                let result = match msg["params"]["name"].as_str() {
                    Some("agent_operations") => Ok(
                        json!({"operations":registry.iter().map(|(name,op)|json!({"name":name,"version":op.version,"description":op.description,"input":"string","output":"string"})).collect::<Vec<_>>()}),
                    ),
                    Some("install_agent_program") => (|| {
                        let name = a["operation"].as_str().ok_or("Missing operation")?;
                        let definition = registry
                            .get(name)
                            .ok_or("Operation is not registered")?
                            .clone();
                        let rules = a["rules"].as_str().ok_or("Missing rules")?;
                        let (program, result) = AgentProgram::install(
                            &mut backend,
                            name,
                            definition,
                            rules,
                            a["schemas"].clone(),
                        )?;
                        agent = Some(program);
                        Ok(result)
                    })(),
                    Some("submit_agent_input") => (|| {
                        agent.as_mut().ok_or("Install an agent program")?.submit(
                            &mut backend,
                            a["entity"].as_str().ok_or("Missing entity")?,
                            a["revision"].as_i64().ok_or("Missing revision")?,
                            a["payload"].as_str().ok_or("Missing payload")?,
                        )
                    })(),
                    Some("claim_agent_request") => (|| {
                        agent.as_mut().ok_or("Install an agent program")?.claim(
                            &mut backend,
                            a["request_id"].as_str().ok_or("Missing request id")?,
                        )
                    })(),
                    Some("complete_agent_request") => (|| {
                        agent.as_mut().ok_or("Install an agent program")?.complete(
                            &mut backend,
                            a["request_id"].as_str().ok_or("Missing request id")?,
                            a["output"].as_str().ok_or("Missing output")?,
                        )
                    })(),
                    Some("agent_request_status") => agent
                        .as_ref()
                        .map(AgentProgram::status)
                        .ok_or("Install an agent program".into()),
                    Some("lemmalog_install_rules") if agent.is_some() => {
                        Err("Start a new session to replace a registered agent program".into())
                    }
                    Some("lemmalog_install_rules") => a["rules"]
                        .as_str()
                        .ok_or("Missing rules".into())
                        .and_then(|r| backend.install(r, a["schemas"].clone())),
                    Some("apply_changes") => {
                        if agent.is_some()
                            && a["changes"].as_array().is_some_and(|changes| {
                                changes.iter().any(|c| {
                                    c["predicate"]
                                        .as_str()
                                        .is_some_and(|p| p.starts_with("agent_"))
                                })
                            })
                        {
                            Err(
                                "Registered operation relations must use the operation tools"
                                    .into(),
                            )
                        } else {
                            backend.apply(&a["changes"])
                        }
                    }
                    Some("lemmalog_query") => a["predicate"]
                        .as_str()
                        .ok_or("Missing predicate".into())
                        .and_then(|p| backend.query(p)),
                    Some("lemmalog_why") => a["rule"]
                        .as_u64()
                        .ok_or("Missing nonnegative rule index".into())
                        .and_then(|r| usize::try_from(r).map_err(|e| e.to_string()))
                        .and_then(|r| backend.why(r)),
                    _ => Err("Unknown tool".into()),
                };
                match result {
                    Ok(v) => {
                        json!({"content":[{"type":"text","text":v.to_string()}],"isError":false})
                    }
                    Err(e) => json!({"content":[{"type":"text","text":e}],"isError":true}),
                }
            }
            _ => {
                writeln!(
                    stdout,
                    "{}",
                    json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"Unknown method"}})
                )?;
                stdout.flush()?;
                continue;
            }
        };
        writeln!(
            stdout,
            "{}",
            json!({"jsonrpc":"2.0","id":id,"result":result})
        )?;
        stdout.flush()?;
    }
    Ok(())
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

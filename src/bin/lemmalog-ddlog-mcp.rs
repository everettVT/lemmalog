//! Experimental MCP surface using the real DDlog backend.
use lemmalog::ddlog::Backend;
use serde_json::{json, Value};
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
            Some("tools/list") => json!({"tools":tools()}),
            Some("tools/call") => {
                let a = &msg["params"]["arguments"];
                let result = match msg["params"]["name"].as_str() {
                    Some("lemmalog_install_rules") => a["rules"]
                        .as_str()
                        .ok_or("Missing rules".into())
                        .and_then(|r| backend.install(r, a["schemas"].clone())),
                    Some("apply_changes") => backend.apply(&a["changes"]),
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

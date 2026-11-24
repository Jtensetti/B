// describe prints the public top-level functions of a Rust crate's src/lib.rs as JSON, read with syn.
// Each function: {"name", "params": [rust type], "result": rust type or null}.
use std::fs;
use quote::ToTokens;

fn main() {
    let path = std::env::args().nth(1).expect("path to lib.rs");
    let source = fs::read_to_string(&path).expect("read lib.rs");
    let file = syn::parse_file(&source).unwrap_or_else(|e| { eprintln!("{e}"); std::process::exit(1) });
    let mut out = Vec::new();
    for item in file.items {
        if let syn::Item::Fn(f) = item {
            if !matches!(f.vis, syn::Visibility::Public(_)) || !f.sig.generics.params.is_empty()
                || f.sig.asyncness.is_some() || f.sig.unsafety.is_some() {
                continue;
            }
            let mut params = Vec::new();
            let mut ok = true;
            for input in &f.sig.inputs {
                match input {
                    syn::FnArg::Typed(t) => params.push(t.ty.to_token_stream().to_string()),
                    _ => ok = false,
                }
            }
            if !ok { continue; }
            let result = match &f.sig.output {
                syn::ReturnType::Default => serde_json::Value::Null,
                syn::ReturnType::Type(_, t) => serde_json::Value::String(t.to_token_stream().to_string()),
            };
            out.push(serde_json::json!({"name": f.sig.ident.to_string(), "params": params, "result": result}));
        }
    }
    println!("{}", serde_json::json!({"functions": out}));
}

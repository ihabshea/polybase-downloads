//! Run only against a disposable benchmark console; existing keys are refused.
use polybase_client::{Client, Query};
use serde_json::json;
use std::time::Instant;
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    assert_eq!(
        args.len(),
        3,
        "ADDRESS PREFIX COUNT on a disposable console"
    );
    let client = Client::new(args[0].parse()?)?;
    let count = args[2].parse::<usize>()?;
    assert!((1..=128).contains(&count));
    let query = Query::all(args[1].as_bytes());
    let session = client.subscribe(&query)?;
    assert!(session.rows.is_empty());
    let started = Instant::now();
    for i in 0..count {
        let key = format!("{}{i:04}", args[1]);
        let read = client.read_revision(key.as_bytes())?;
        assert!(read.value.is_none());
        let value = json!({"client":"rust","n":i}).to_string();
        let receipt = client.write_revision(&read.revision, Some(value.as_bytes()))?;
        assert!(receipt.durable);
    }
    let write_us = started.elapsed().as_micros();
    let started = Instant::now();
    let page = client.page(&query, None, 128)?;
    assert_eq!(page.rows.len(), count);
    let page_us = started.elapsed().as_micros();
    let started = Instant::now();
    let delta = client.poll(&session, &session.token)?;
    assert_eq!(delta.commits.len(), count);
    let poll_us = started.elapsed().as_micros();
    client.unsubscribe(&session, &delta.token)?;
    println!(
        "{}",
        json!({"client":"rust","records":count,"revision_read_write_us":write_us,"page_us":page_us,"poll_us":poll_us,"correctness_verified":true})
    );
    Ok(())
}

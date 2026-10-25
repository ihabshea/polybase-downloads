//! Stream recorded observations through the independent QA specification.
//! No engine implementation, runtime connection or consensus-log oracle is used.
mod checker;

use checker::{CheckResult, History};
use serde::{
    Deserialize, Serialize,
    de::{self, MapAccess, SeqAccess, Visitor},
};
use serde_json::{Value, json};
use std::{
    env, fmt,
    io::{self, BufRead, Write},
    process::ExitCode,
};

const MAX_LINE_BYTES: usize = 16 * 1024 * 1024;
const MAX_RECORDS: usize = 100_000;
const MAX_BUDGET: usize = 1_000_000;
const CHECKER_SHA256: &str = "9b9e18dd96d112b531183815260e71434680fcdb74cb28566486a3b8cba31e7e";

#[derive(Clone, Copy, Debug)]
struct Config {
    budget: usize,
    minimize_failures: bool,
}

enum Arguments {
    Run(Config),
    Help,
}

fn arguments(input: impl IntoIterator<Item = String>) -> Result<Arguments, String> {
    let mut config = Config {
        budget: 200_000,
        minimize_failures: false,
    };
    let mut budget_seen = false;
    let mut input = input.into_iter();
    while let Some(arg) = input.next() {
        match arg.as_str() {
            "--help" | "-h" => return Ok(Arguments::Help),
            "--budget" if !budget_seen => {
                budget_seen = true;
                config.budget = input
                    .next()
                    .ok_or("missing --budget value")?
                    .parse()
                    .map_err(|_| "--budget must be an integer")?;
            }
            "--minimize-failures" if !config.minimize_failures => config.minimize_failures = true,
            _ => return Err(format!("unknown or repeated argument: {arg}")),
        }
    }
    if !(1..=MAX_BUDGET).contains(&config.budget) {
        return Err("--budget must be between 1 and 1000000 states".into());
    }
    Ok(Arguments::Run(config))
}

enum Line {
    End,
    Bytes(Vec<u8>),
    Oversize,
}

fn bounded_line(input: &mut impl BufRead) -> io::Result<Line> {
    let mut line = Vec::new();
    loop {
        let available = input.fill_buf()?;
        if available.is_empty() {
            return Ok(if line.is_empty() {
                Line::End
            } else {
                Line::Bytes(line)
            });
        }
        let newline = available.iter().position(|&byte| byte == b'\n');
        let length = newline.map_or(available.len(), |offset| offset + 1);
        if line.len().saturating_add(length) > MAX_LINE_BYTES {
            return Ok(Line::Oversize);
        }
        line.extend_from_slice(&available[..length]);
        input.consume(length);
        if newline.is_some() {
            return Ok(Line::Bytes(line));
        }
    }
}

fn emit(output: &mut impl Write, value: &impl Serialize) -> io::Result<()> {
    serde_json::to_writer(&mut *output, value)?;
    output.write_all(b"\n")?;
    output.flush()
}

fn invalid(reason: impl Into<String>) -> CheckResult {
    CheckResult::Invalid {
        reason: reason.into(),
    }
}

fn history_value(value: &Value) -> &Value {
    let record = value
        .get("minimized")
        .or_else(|| value.get("record"))
        .unwrap_or(value);
    record.get("history").unwrap_or(record)
}

/// Preserve JSON's tree while rejecting duplicate names at every depth, before
/// selecting an envelope or deserializing the strict versioned history schema.
struct StrictValue(Value);

impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D: de::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct StrictVisitor;
        impl<'de> Visitor<'de> for StrictVisitor {
            type Value = StrictValue;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("JSON without duplicate object fields")
            }
            fn visit_unit<E: de::Error>(self) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Null))
            }
            fn visit_bool<E: de::Error>(self, value: bool) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Bool(value)))
            }
            fn visit_i64<E: de::Error>(self, value: i64) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Number(value.into())))
            }
            fn visit_u64<E: de::Error>(self, value: u64) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Number(value.into())))
            }
            fn visit_f64<E: de::Error>(self, value: f64) -> Result<Self::Value, E> {
                serde_json::Number::from_f64(value)
                    .map(|number| StrictValue(Value::Number(number)))
                    .ok_or_else(|| E::custom("nonfinite JSON number"))
            }
            fn visit_str<E: de::Error>(self, value: &str) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::String(value.into())))
            }
            fn visit_string<E: de::Error>(self, value: String) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::String(value)))
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut sequence: A,
            ) -> Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(StrictValue(value)) = sequence.next_element()? {
                    values.push(value);
                }
                Ok(StrictValue(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut mapping: A) -> Result<Self::Value, A::Error> {
                let mut values = serde_json::Map::new();
                while let Some(key) = mapping.next_key::<String>()? {
                    if values.contains_key(&key) {
                        return Err(de::Error::custom("duplicate JSON object field"));
                    }
                    let StrictValue(value) = mapping.next_value()?;
                    values.insert(key, value);
                }
                Ok(StrictValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(StrictVisitor)
    }
}

fn process(bytes: &[u8], config: Config) -> (Option<History>, CheckResult) {
    let value: Value = match serde_json::from_slice::<StrictValue>(bytes) {
        Ok(StrictValue(value)) => value,
        Err(error) => {
            return (
                None,
                invalid(
                    format!("invalid_json: {error}")
                        .chars()
                        .take(512)
                        .collect::<String>(),
                ),
            );
        }
    };
    let history: History = match serde_json::from_value(history_value(&value).clone()) {
        Ok(history) => history,
        Err(error) => {
            return (
                None,
                invalid(
                    format!("invalid_history_schema: {error}")
                        .chars()
                        .take(512)
                        .collect::<String>(),
                ),
            );
        }
    };
    let result = checker::check(&history, config.budget);
    (Some(history), result)
}

#[derive(Default, Serialize)]
struct Summary {
    schema: u32,
    #[serde(rename = "type")]
    kind: &'static str,
    records: usize,
    linearizable: usize,
    violations: usize,
    inconclusive: usize,
    invalid: usize,
    all_passed: bool,
    engine_executed: bool,
    checker_source_sha256: &'static str,
    search_state_budget: usize,
    input_stopped_at_limit: bool,
}

fn run(input: &mut impl BufRead, output: &mut impl Write, config: Config) -> io::Result<Summary> {
    let mut summary = Summary {
        schema: 1,
        kind: "summary",
        checker_source_sha256: CHECKER_SHA256,
        search_state_budget: config.budget,
        ..Summary::default()
    };
    loop {
        let read = bounded_line(input);
        let (history, result, stop) = match read {
            Ok(Line::End) => break,
            Ok(Line::Bytes(_)) if summary.records >= MAX_RECORDS => {
                summary.input_stopped_at_limit = true;
                (None, invalid("record_limit_exceeded"), true)
            }
            Ok(Line::Bytes(bytes)) => {
                let (history, result) = process(&bytes, config);
                (history, result, false)
            }
            Ok(Line::Oversize) => {
                summary.input_stopped_at_limit = true;
                (
                    None,
                    invalid("input_line_exceeds_16_mib_including_line_ending"),
                    true,
                )
            }
            Err(error) => (None, invalid(format!("input_io_error: {error}")), true),
        };
        summary.records += 1;
        match &result {
            CheckResult::Linearizable { .. } => summary.linearizable += 1,
            CheckResult::Violation { .. } => summary.violations += 1,
            CheckResult::Inconclusive { .. } => summary.inconclusive += 1,
            CheckResult::Invalid { .. } => summary.invalid += 1,
        }
        let reduction =
            if config.minimize_failures && matches!(result, CheckResult::Violation { .. }) {
                history
                    .as_ref()
                    .map(|history| checker::minimize(history, config.budget, 4096))
            } else {
                None
            };
        emit(
            output,
            &json!({"schema":1,"type":"record","line":summary.records,
            "history_id":history.as_ref().map(|h|h.history_id),"seed":history.as_ref().map(|h|h.seed),
            "result":result,"passed":result.is_linearizable(),"states_explored":result.explored(),"reason":result.reason(),
            "reduction":reduction,"engine_executed":false,"checker_source_sha256":CHECKER_SHA256}),
        )?;
        if stop {
            break;
        }
    }
    summary.all_passed = summary.records > 0 && summary.linearizable == summary.records;
    emit(output, &summary)?;
    Ok(summary)
}

fn main() -> ExitCode {
    let config = match arguments(env::args().skip(1)) {
        Ok(Arguments::Run(config)) => config,
        Ok(Arguments::Help) => {
            println!(
                "atlas-history-checker [--budget 1..1000000] [--minimize-failures]\nReads one History or record/minimized envelope per JSON input line; emits one result per record and an EOF summary. Default budget: 200000 states. At most 100000 histories and 16 MiB per input line including ending. Malformed JSON/schema continues; input-size/record limits stop immediately with an invalid result. Exit 0 only for nonempty all-linearizable input. Local prefix observations are not quorum freshness; unknown writes may commit after timeout. No engine executes. MIT license covers this QA package only."
            );
            return ExitCode::SUCCESS;
        }
        Err(error) => {
            eprintln!("atlas-history-checker: {error}");
            return ExitCode::from(2);
        }
    };
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    match run(&mut input, &mut output, config) {
        Ok(summary) if summary.all_passed => ExitCode::SUCCESS,
        Ok(_) => ExitCode::FAILURE,
        Err(error) => {
            eprintln!("atlas-history-checker: output failed: {error}");
            ExitCode::from(2)
        }
    }
}

#[cfg(test)]
mod cli_tests {
    use super::*;
    use std::io::Cursor;

    fn config() -> Config {
        Config {
            budget: 200_000,
            minimize_failures: false,
        }
    }
    fn history() -> Value {
        json!({"schema":1,"engine_version":"SYNTHETIC-CONTROL","seed":42,"history_id":7,
            "profile":"synthetic","cluster_id":"test-cluster","membership_generation":0,
            "failure_point":null,"replay_command":"synthetic-control-only",
            "initial":{"position":{"index":0,"term":0},"rows":[],"requests":[]},
            "operations":[{"id":1,"client":1,"node":1,"invocation":1,"response":2,
                "call":{"call":"read","mode":"quorum","minimum":null,"query":{"query":"prefix","prefix":[]}},
                "outcome":{"outcome":"snapshot","position":{"index":0,"term":0},"rows":[]}}]})
    }
    fn stream(values: &[Value], cfg: Config) -> (Summary, Vec<Value>) {
        let bytes = values
            .iter()
            .map(|v| serde_json::to_string(v).unwrap())
            .collect::<Vec<_>>()
            .join("\n");
        let mut output = Vec::new();
        let summary = run(&mut Cursor::new(bytes), &mut output, cfg).unwrap();
        let records = String::from_utf8(output)
            .unwrap()
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect();
        (summary, records)
    }
    #[test]
    fn accepts_plain_and_both_envelopes_and_outputs_one_summary() {
        let h = history();
        let (summary, output) = stream(
            &[
                h.clone(),
                json!({"record":{"history":h}}),
                json!({"minimized":history()}),
            ],
            config(),
        );
        assert!(summary.all_passed);
        assert_eq!(summary.records, 3);
        assert_eq!(output.len(), 4);
        assert_eq!(output[0]["history_id"], 7);
        assert_eq!(output[3]["type"], "summary");
    }
    #[test]
    fn wrong_observation_and_exhausted_budget_cannot_pass() {
        let mut wrong = history();
        wrong["operations"][0]["outcome"]["rows"] = json!([[[1], [9]]]);
        let (summary, output) = stream(
            &[wrong],
            Config {
                minimize_failures: true,
                ..config()
            },
        );
        assert!(!summary.all_passed);
        assert_eq!(summary.violations, 1);
        assert!(output[0]["reduction"].is_object());
        let mut h = history();
        let mut second = h["operations"][0].clone();
        second["id"] = 2.into();
        second["invocation"] = 3.into();
        second["response"] = 4.into();
        h["operations"].as_array_mut().unwrap().push(second);
        let (summary, _) = stream(
            &[h],
            Config {
                budget: 1,
                ..config()
            },
        );
        assert_eq!(summary.inconclusive, 1);
        assert!(!summary.all_passed);
    }
    #[test]
    fn malformed_record_continues_and_empty_stream_fails() {
        let bytes = format!("not-json\n{}\n", history());
        let mut output = Vec::new();
        let summary = run(&mut Cursor::new(bytes), &mut output, config()).unwrap();
        assert_eq!(
            (summary.records, summary.invalid, summary.linearizable),
            (2, 1, 1)
        );
        assert!(!summary.all_passed);
        let (empty, records) = stream(&[], config());
        assert!(!empty.all_passed);
        assert_eq!(records.len(), 1);
    }
    #[test]
    fn duplicate_fields_are_rejected_recursively_before_envelope_selection() {
        let original = history().to_string();
        let root_duplicate = original.replace("\"seed\":42", "\"seed\":42,\"seed\":99");
        let nested_duplicate = original.replace("\"rows\":[]", "\"rows\":[],\"rows\":[]");
        let outcome_duplicate = original.replace(
            "\"outcome\":\"snapshot\"",
            "\"outcome\":\"snapshot\",\"outcome\":\"snapshot\"",
        );
        assert_ne!(root_duplicate, original);
        assert_ne!(nested_duplicate, original);
        for candidate in [
            root_duplicate,
            nested_duplicate,
            outcome_duplicate,
            "{\"rows\":[{\"key\":[1],\"value\":[9],\"key\":[2]}]}".into(),
            [
                "{\"record\":{\"history\":",
                &original,
                "},\"record\":{\"history\":",
                &original,
                "}}",
            ]
            .concat(),
            "{\"outer\":[{\"x\":1,\"\\u0078\":2}]}".into(),
        ] {
            let (_, result) = process(candidate.as_bytes(), config());
            assert!(matches!(result, CheckResult::Invalid { .. }));
            assert!(
                result
                    .reason()
                    .unwrap()
                    .contains("duplicate JSON object field")
            );
        }
        // Repeated key strings in different objects are legitimate.
        assert!(process(original.as_bytes(), config()).1.is_linearizable());
    }
    #[test]
    fn line_limit_stops_without_unbounded_buffering() {
        let mut output = Vec::new();
        let summary = run(
            &mut Cursor::new(vec![b'x'; MAX_LINE_BYTES + 1]),
            &mut output,
            config(),
        )
        .unwrap();
        assert_eq!(summary.invalid, 1);
        assert!(summary.input_stopped_at_limit);
        assert!(!summary.all_passed);
    }
    #[test]
    fn first_record_beyond_limit_is_reported_and_input_stops() {
        let input = b"null\n".repeat(MAX_RECORDS + 2);
        let mut input = Cursor::new(input);
        let summary = run(&mut input, &mut io::sink(), config()).unwrap();
        assert_eq!(summary.records, MAX_RECORDS + 1);
        assert_eq!(summary.invalid, MAX_RECORDS + 1);
        assert!(summary.input_stopped_at_limit);
        assert!(!summary.all_passed);
        assert!(input.position() < input.get_ref().len() as u64);
    }
    #[test]
    fn arguments_are_bounded_and_unrecognized_flags_fail() {
        assert!(arguments(["--budget".into(), "0".into()]).is_err());
        assert!(arguments(["--budget".into(), "1000001".into()]).is_err());
        assert!(arguments(["--wat".into()]).is_err());
        assert!(matches!(arguments(["--help".into()]), Ok(Arguments::Help)));
    }
}

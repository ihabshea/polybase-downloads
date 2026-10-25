//! Independent bounded cluster-history specification.
//!
//! Quorum observations are linearizable. Local observations are checked against
//! an identified committed prefix and may be stale; they are not promoted to
//! quorum reads. A timed-out write remains pending through the captured history.
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, HashSet};

pub type Entries = Vec<(Vec<u8>, Vec<u8>)>;

#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
#[serde(deny_unknown_fields)]
pub struct Position {
    pub index: u64,
    pub term: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Expected {
    pub key: Vec<u8>,
    pub value: Option<Vec<u8>>,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(tag = "mutation", rename_all = "snake_case", deny_unknown_fields)]
pub enum Mutation {
    Put { key: Vec<u8>, value: Vec<u8> },
    Delete { key: Vec<u8> },
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Transaction {
    pub expected: Vec<Expected>,
    pub mutations: Vec<Mutation>,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(tag = "query", rename_all = "snake_case", deny_unknown_fields)]
pub enum Query {
    Point {
        key: Vec<u8>,
    },
    Range {
        start: Option<Vec<u8>>,
        end: Option<Vec<u8>>,
    },
    Prefix {
        prefix: Vec<u8>,
    },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReadMode {
    Quorum,
    Local,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(tag = "call", rename_all = "snake_case", deny_unknown_fields)]
pub enum Call {
    Write {
        /// Canonical decoded identity, not an alias such as upper-case hex.
        request_id: String,
        intent: Transaction,
    },
    Read {
        mode: ReadMode,
        minimum: Option<Position>,
        query: Query,
    },
    /// Quorum-confirmed retained request lookup. Expiry is outside this model.
    Outcome {
        request_id: String,
        intent: Option<Transaction>,
    },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Applied,
    Conflict,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(tag = "outcome", rename_all = "snake_case", deny_unknown_fields)]
pub enum Outcome {
    Receipt {
        position: Position,
        status: Status,
        replayed: bool,
    },
    Snapshot {
        position: Position,
        rows: Entries,
    },
    Absent {},
    /// Guaranteed admission rejection: never submitted, never chosen.
    DefinitiveAbort {
        reason: String,
    },
    /// Write may commit after the timeout. Never treated as a definite abort.
    Unknown {
        reason: String,
    },
    /// Reusing a retained identity with different intent, with no mutation.
    RequestMismatch {},
}

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Operation {
    pub id: u64,
    pub client: u32,
    pub node: u64,
    pub invocation: u64,
    pub response: u64,
    pub call: Call,
    pub outcome: Outcome,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RetainedRequest {
    pub request_id: String,
    pub intent: Transaction,
    pub position: Position,
    pub status: Status,
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InitialState {
    pub position: Position,
    pub rows: Entries,
    pub requests: Vec<RetainedRequest>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct History {
    pub schema: u32,
    pub engine_version: String,
    pub seed: u64,
    pub history_id: u64,
    pub profile: String,
    pub cluster_id: String,
    pub membership_generation: u64,
    pub failure_point: Option<String>,
    pub replay_command: String,
    pub initial: InitialState,
    pub operations: Vec<Operation>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WitnessStep {
    pub operation: u64,
    /// Unknown calls may be omitted or completed; retained receipts are reused.
    pub effect: String,
    pub position: Option<Position>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Reduction {
    pub history: History,
    pub result: CheckResult,
    pub attempts: usize,
    /// Only whole read/outcome observations are candidates for deletion. Every
    /// write, including an ambiguous one, and the complete initial context stay.
    pub context_preserving_one_minimal: bool,
    pub limitation: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum CheckResult {
    Linearizable {
        witness: Vec<WitnessStep>,
        explored: usize,
        local_prefix_reads: usize,
    },
    Violation {
        reason: String,
        explored: usize,
    },
    Inconclusive {
        reason: String,
        explored: usize,
    },
    Invalid {
        reason: String,
    },
}

impl CheckResult {
    pub fn is_linearizable(&self) -> bool {
        matches!(self, Self::Linearizable { .. })
    }
    pub fn explored(&self) -> usize {
        match self {
            Self::Linearizable { explored, .. }
            | Self::Violation { explored, .. }
            | Self::Inconclusive { explored, .. } => *explored,
            Self::Invalid { .. } => 0,
        }
    }
    pub fn reason(&self) -> Option<&str> {
        match self {
            Self::Linearizable { .. } => None,
            Self::Violation { reason, .. }
            | Self::Inconclusive { reason, .. }
            | Self::Invalid { reason } => Some(reason),
        }
    }
}

const MAX_OPERATIONS: usize = 64;
const MAX_FIELDS: usize = 64;
const MAX_INPUT_BYTES: usize = 8 * 1024 * 1024;
const MAX_MODEL_BYTES: usize = 512 * 1024;
const MAX_MODEL_ROWS: usize = 4096;
const MAX_MEMO_BYTES: usize = 32 * 1024 * 1024;
const MAX_SEARCH_STATES: usize = 1_000_000;

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
struct StoredRequest {
    intent: Transaction,
    position: Position,
    status: Status,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
struct Model {
    head: Position,
    rows: BTreeMap<Vec<u8>, Vec<u8>>,
    requests: BTreeMap<String, StoredRequest>,
}

impl Model {
    fn charge(&self) -> usize {
        self.rows
            .iter()
            .fold(0usize, |n, (k, v)| {
                n.saturating_add(k.len())
                    .saturating_add(v.len())
                    .saturating_add(64)
            })
            .saturating_add(self.requests.iter().fold(0usize, |n, (id, request)| {
                n.saturating_add(id.len())
                    .saturating_add(transaction_charge(&request.intent))
                    .saturating_add(128)
            }))
    }

    fn bounded(&self) -> bool {
        self.rows.len() <= MAX_MODEL_ROWS && self.charge() <= MAX_MODEL_BYTES
    }
}

struct Search<'a> {
    history: &'a History,
    predecessors: Vec<u64>,
    anchors: BTreeMap<String, Position>,
    observed_terms: BTreeMap<u64, u64>,
    budget: usize,
    explored: usize,
    memo_bytes: usize,
    dead: HashSet<(u64, Model)>,
    witness: Vec<WitnessStep>,
    truncated: Option<&'static str>,
}

/// Search limit is a count of explored specification states, not a duration.
///
/// The result's `local_prefix_reads` distinguishes explicitly stale reads from
/// quorum operations. The witness is a linearization of quorum operations plus
/// prefix placements for local reads, never a claim that stale reads satisfy
/// real-time freshness. Timed-out writes can be omitted or completed at any
/// later point after invocation, including after their timeout response.
pub fn check(history: &History, budget: usize) -> CheckResult {
    if let Err(reason) = validate(history, budget) {
        return CheckResult::Invalid { reason };
    }
    let mut observed_terms = BTreeMap::new();
    let mut anchors = BTreeMap::new();
    let mut positions = vec![history.initial.position];
    for request in &history.initial.requests {
        anchors.insert(request.request_id.clone(), request.position);
        positions.push(request.position);
    }
    for op in &history.operations {
        match &op.outcome {
            Outcome::Receipt { position, .. } => {
                positions.push(*position);
                let Some(id) = request_identity(&op.call) else {
                    return CheckResult::Invalid {
                        reason: "receipt_without_request".into(),
                    };
                };
                if let Some(previous) = anchors.insert(id.to_owned(), *position)
                    && previous != *position
                {
                    return CheckResult::Violation {
                        reason: "named_request_changed_original_position".into(),
                        explored: 0,
                    };
                }
            }
            Outcome::Snapshot { position, .. } => positions.push(*position),
            _ => {}
        }
        if let Call::Read {
            minimum: Some(position),
            ..
        } = &op.call
        {
            positions.push(*position);
        }
    }
    for position in positions {
        if let Some(previous) = observed_terms.insert(position.index, position.term)
            && previous != position.term
        {
            return CheckResult::Violation {
                reason: "conflicting_terms_at_committed_index".into(),
                explored: 0,
            };
        }
    }
    if !observed_terms.values().is_sorted() {
        return CheckResult::Violation {
            reason: "committed_terms_regress".into(),
            explored: 0,
        };
    }
    let model = Model {
        head: history.initial.position,
        rows: history.initial.rows.iter().cloned().collect(),
        requests: history
            .initial
            .requests
            .iter()
            .map(|r| {
                (
                    r.request_id.clone(),
                    StoredRequest {
                        intent: r.intent.clone(),
                        position: r.position,
                        status: r.status,
                    },
                )
            })
            .collect(),
    };
    if !model.bounded() {
        return CheckResult::Inconclusive {
            reason: "initial_model_budget".into(),
            explored: 0,
        };
    }
    let predecessors = history
        .operations
        .iter()
        .map(|target| {
            if local_read(target) {
                // Its declared applied prefix can predate already acknowledged writes.
                return 0;
            }
            history
                .operations
                .iter()
                .enumerate()
                .fold(0u64, |mask, (i, source)| {
                    if source.response < target.invocation && !pending_write(source) {
                        mask | (1u64 << i)
                    } else {
                        mask
                    }
                })
        })
        .collect();
    let mut search = Search {
        history,
        predecessors,
        anchors,
        observed_terms,
        budget,
        explored: 0,
        memo_bytes: 0,
        dead: HashSet::new(),
        witness: Vec::new(),
        truncated: None,
    };
    if search.visit(0, &model) {
        return CheckResult::Linearizable {
            witness: search.witness,
            explored: search.explored,
            local_prefix_reads: history
                .operations
                .iter()
                .filter(|op| local_read(op))
                .count(),
        };
    }
    if let Some(reason) = search.truncated {
        CheckResult::Inconclusive {
            reason: reason.into(),
            explored: search.explored,
        }
    } else {
        CheckResult::Violation {
            reason: "no_interval_compatible_atomic_cluster_history".into(),
            explored: search.explored,
        }
    }
}

/// Deterministic observation reduction, never deletion of mutation producers or
/// renumbering of positions. This does not minimize a network/OS fault schedule.
pub fn minimize(history: &History, budget: usize, max_checks: usize) -> Reduction {
    let mut reduced = history.clone();
    let mut result = check(history, budget);
    let class = result.reason().map(str::to_owned);
    let mut attempts = 0;
    let mut complete = matches!(result, CheckResult::Violation { .. });
    if complete {
        let mut i = 0;
        while i < reduced.operations.len() {
            if matches!(reduced.operations[i].call, Call::Write { .. }) {
                i += 1;
                continue;
            }
            if attempts >= max_checks.min(10_000) {
                complete = false;
                break;
            }
            let mut candidate = reduced.clone();
            candidate.operations.remove(i);
            attempts += 1;
            let candidate_result = check(&candidate, budget);
            if matches!(candidate_result, CheckResult::Violation { .. })
                && candidate_result.reason() == class.as_deref()
            {
                reduced = candidate;
                result = candidate_result;
                i = 0;
            } else {
                if matches!(
                    candidate_result,
                    CheckResult::Inconclusive { .. } | CheckResult::Invalid { .. }
                ) {
                    complete = false;
                }
                i += 1;
            }
        }
    }
    Reduction {
        history: reduced, result, attempts, context_preserving_one_minimal: complete,
        limitation: "One-minimal only among whole read/outcome observation deletions; all writes, initial state, identities, positions and intervals are preserved. Not a globally minimal workload or deterministic OS/network-schedule replay.".into(),
    }
}

impl Search<'_> {
    fn visit(&mut self, mask: u64, model: &Model) -> bool {
        if mask.count_ones() as usize == self.history.operations.len() {
            return true;
        }
        if self.explored >= self.budget {
            self.truncated.get_or_insert("search_state_budget");
            return false;
        }
        self.explored += 1;
        if self.dead.contains(&(mask, model.clone())) {
            return false;
        }
        for i in 0..self.history.operations.len() {
            let bit = 1u64 << i;
            if mask & bit != 0 || self.predecessors[i] & !mask != 0 {
                continue;
            }
            let op = &self.history.operations[i];
            // An unresolved call can have no visible effect. Its alternate
            // completion is separately searched; no observed read is invented.
            if matches!(op.outcome, Outcome::Unknown { .. }) {
                self.witness.push(WitnessStep {
                    operation: op.id,
                    effect: "unknown_omitted".into(),
                    position: None,
                });
                if self.visit(mask | bit, model) {
                    return true;
                }
                self.witness.pop();
            }
            if let Some((next, step)) = self.apply(op, model) {
                if !next.bounded() {
                    self.truncated.get_or_insert("model_state_budget");
                    continue;
                }
                self.witness.push(step);
                if self.visit(mask | bit, &next) {
                    return true;
                }
                self.witness.pop();
            }
        }
        let charge = model.charge().saturating_add(128);
        if self.memo_bytes.saturating_add(charge) > MAX_MEMO_BYTES {
            self.truncated.get_or_insert("memo_memory_budget");
        } else {
            self.memo_bytes += charge;
            self.dead.insert((mask, model.clone()));
        }
        false
    }

    fn apply(&self, op: &Operation, model: &Model) -> Option<(Model, WitnessStep)> {
        let mut next = model.clone();
        let mut effect = "definitive_abort";
        let mut witness_position = None;
        match (&op.call, &op.outcome) {
            (_, Outcome::DefinitiveAbort { .. }) => {}
            (
                Call::Write { request_id, intent },
                Outcome::Receipt {
                    position,
                    status,
                    replayed,
                },
            ) => {
                if let Some(stored) = model.requests.get(request_id) {
                    if stored.intent != *intent
                        || stored.position != *position
                        || stored.status != *status
                        || !replayed
                    {
                        return None;
                    }
                    effect = "named_replay";
                } else {
                    if *replayed || !advance(&mut next, *position, true) {
                        return None;
                    }
                    let expected = evaluate(intent, &model.rows);
                    if *status != expected {
                        return None;
                    }
                    choose(&mut next, request_id, intent, *position, expected);
                    effect = if expected == Status::Applied {
                        "applied"
                    } else {
                        "conflict"
                    };
                }
                witness_position = Some(*position);
            }
            (Call::Write { request_id, intent }, Outcome::Unknown { .. }) => {
                if let Some(stored) = model.requests.get(request_id) {
                    if stored.intent != *intent {
                        return None;
                    }
                    witness_position = Some(stored.position);
                    effect = "unknown_named_replay";
                } else {
                    let position = if let Some(position) = self.anchors.get(request_id) {
                        *position
                    } else {
                        let index = model.head.index.checked_add(1)?;
                        // The least available index is a sound representative:
                        // all future fixed-position constraints are upper bounds.
                        let term = self
                            .observed_terms
                            .range(..=index)
                            .next_back()
                            .map_or(1, |(_, term)| (*term).max(1));
                        Position { index, term }
                    };
                    if !advance(&mut next, position, true) {
                        return None;
                    }
                    let status = evaluate(intent, &model.rows);
                    choose(&mut next, request_id, intent, position, status);
                    witness_position = Some(position);
                    effect = if status == Status::Applied {
                        "unknown_completed_applied"
                    } else {
                        "unknown_completed_conflict"
                    };
                }
            }
            (
                Call::Read {
                    minimum,
                    query,
                    mode,
                },
                Outcome::Snapshot { position, rows },
            ) => {
                if minimum.is_some_and(|p| {
                    position.index < p.index
                        || (position.index == p.index && position.term != p.term)
                }) {
                    return None;
                }
                if !advance(&mut next, *position, false) || query_rows(query, &model.rows) != *rows
                {
                    return None;
                }
                effect = if *mode == ReadMode::Local {
                    "local_prefix"
                } else {
                    "quorum_read"
                };
                witness_position = Some(*position);
            }
            (
                Call::Outcome { request_id, intent },
                Outcome::Receipt {
                    position,
                    status,
                    replayed,
                },
            ) => {
                let stored = model.requests.get(request_id)?;
                if intent
                    .as_ref()
                    .is_some_and(|intent| *intent != stored.intent)
                    || stored.position != *position
                    || stored.status != *status
                    || *replayed
                {
                    return None;
                }
                effect = "outcome_found";
                witness_position = Some(*position);
            }
            (Call::Outcome { request_id, .. }, Outcome::Absent {}) => {
                if model.requests.contains_key(request_id) {
                    return None;
                }
                effect = "outcome_absent";
            }
            (Call::Write { request_id, intent }, Outcome::RequestMismatch {})
            | (
                Call::Outcome {
                    request_id,
                    intent: Some(intent),
                },
                Outcome::RequestMismatch {},
            ) => {
                let stored = model.requests.get(request_id)?;
                if *intent == stored.intent {
                    return None;
                }
                effect = "request_mismatch";
                witness_position = Some(stored.position);
            }
            _ => return None,
        }
        Some((
            next,
            WitnessStep {
                operation: op.id,
                effect: effect.into(),
                position: witness_position,
            },
        ))
    }
}

fn advance(model: &mut Model, position: Position, strict: bool) -> bool {
    if position.index < model.head.index
        || (strict && position.index == model.head.index)
        || position.term < model.head.term
        || (position.index == model.head.index && position.term != model.head.term)
    {
        return false;
    }
    model.head = position;
    true
}

fn evaluate(intent: &Transaction, rows: &BTreeMap<Vec<u8>, Vec<u8>>) -> Status {
    if intent
        .expected
        .iter()
        .all(|e| rows.get(&e.key) == e.value.as_ref())
    {
        Status::Applied
    } else {
        Status::Conflict
    }
}

fn choose(model: &mut Model, id: &str, intent: &Transaction, position: Position, status: Status) {
    if status == Status::Applied {
        for mutation in &intent.mutations {
            match mutation {
                Mutation::Put { key, value } => {
                    model.rows.insert(key.clone(), value.clone());
                }
                Mutation::Delete { key } => {
                    model.rows.remove(key);
                }
            }
        }
    }
    model.requests.insert(
        id.into(),
        StoredRequest {
            intent: intent.clone(),
            position,
            status,
        },
    );
}

fn query_rows(query: &Query, rows: &BTreeMap<Vec<u8>, Vec<u8>>) -> Entries {
    rows.iter()
        .filter(|(key, _)| match query {
            Query::Point { key: wanted } => *key == wanted,
            Query::Prefix { prefix } => key.starts_with(prefix),
            Query::Range { start, end } => {
                start.as_ref().is_none_or(|s| *key >= s) && end.as_ref().is_none_or(|e| *key < e)
            }
        })
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect()
}

fn local_read(op: &Operation) -> bool {
    matches!(
        op.call,
        Call::Read {
            mode: ReadMode::Local,
            ..
        }
    ) && matches!(op.outcome, Outcome::Snapshot { .. })
}

fn pending_write(op: &Operation) -> bool {
    matches!(op.call, Call::Write { .. }) && matches!(op.outcome, Outcome::Unknown { .. })
}

fn request_identity(call: &Call) -> Option<&str> {
    match call {
        Call::Write { request_id, .. } | Call::Outcome { request_id, .. } => Some(request_id),
        Call::Read { .. } => None,
    }
}

fn transaction_charge(t: &Transaction) -> usize {
    let mut bytes = t.expected.iter().fold(0usize, |n, e| {
        n.saturating_add(e.key.len())
            .saturating_add(e.value.as_ref().map_or(0, Vec::len))
            .saturating_add(64)
    });
    for mutation in &t.mutations {
        bytes = bytes
            .saturating_add(match mutation {
                Mutation::Put { key, value } => key.len().saturating_add(value.len()),
                Mutation::Delete { key } => key.len(),
            })
            .saturating_add(64);
    }
    bytes
}

fn sorted_rows(rows: &Entries) -> bool {
    rows.windows(2).all(|pair| pair[0].0 < pair[1].0)
}

fn valid_position(p: Position) -> bool {
    (p.index == 0) == (p.term == 0)
}

fn validate(history: &History, budget: usize) -> Result<(), String> {
    if history.schema != 1 {
        return Err("unsupported_history_schema".into());
    }
    if history.engine_version.is_empty()
        || history.profile.is_empty()
        || history.cluster_id.is_empty()
        || history.replay_command.is_empty()
    {
        return Err("missing_replay_provenance".into());
    }
    if budget == 0 || budget > MAX_SEARCH_STATES {
        return Err("invalid_search_budget".into());
    }
    if history.operations.len() > MAX_OPERATIONS {
        return Err("operation_limit".into());
    }
    if history.initial.rows.len() > MAX_MODEL_ROWS
        || history.initial.requests.len() > MAX_MODEL_ROWS
    {
        return Err("initial_row_or_request_limit".into());
    }
    // Bound logical input before serde allocates an encoded copy. Container
    // overhead is charged as well as payloads, including empty byte strings.
    let mut input_bytes = history
        .engine_version
        .len()
        .saturating_add(history.profile.len())
        .saturating_add(history.cluster_id.len())
        .saturating_add(history.replay_command.len())
        .saturating_add(history.failure_point.as_ref().map_or(0, String::len))
        .saturating_add(entries_charge(&history.initial.rows));
    for request in &history.initial.requests {
        validate_transaction(&request.intent)?;
        input_bytes = input_bytes
            .saturating_add(request.request_id.len())
            .saturating_add(transaction_charge(&request.intent))
            .saturating_add(128);
    }
    for op in &history.operations {
        match &op.call {
            Call::Write { intent, .. }
            | Call::Outcome {
                intent: Some(intent),
                ..
            } => {
                validate_transaction(intent)?;
            }
            _ => {}
        }
        input_bytes = input_bytes
            .saturating_add(256)
            .saturating_add(match &op.call {
                Call::Write { request_id, intent } => {
                    request_id.len().saturating_add(transaction_charge(intent))
                }
                Call::Outcome { request_id, intent } => request_id
                    .len()
                    .saturating_add(intent.as_ref().map_or(0, transaction_charge)),
                Call::Read { query, .. } => match query {
                    Query::Point { key } => key.len(),
                    Query::Prefix { prefix } => prefix.len(),
                    Query::Range { start, end } => start
                        .as_ref()
                        .map_or(0, Vec::len)
                        .saturating_add(end.as_ref().map_or(0, Vec::len)),
                },
            });
        input_bytes = input_bytes.saturating_add(match &op.outcome {
            Outcome::Snapshot { rows, .. } => {
                if rows.len() > MAX_MODEL_ROWS {
                    return Err("observation_row_limit".into());
                }
                entries_charge(rows)
            }
            Outcome::Unknown { reason } | Outcome::DefinitiveAbort { reason } => reason.len(),
            _ => 0,
        });
    }
    if input_bytes > MAX_INPUT_BYTES {
        return Err("input_byte_limit".into());
    }
    if !valid_position(history.initial.position) || !sorted_rows(&history.initial.rows) {
        return Err("invalid_initial_state".into());
    }
    let mut ids = BTreeSet::new();
    let mut requests = BTreeSet::new();
    let mut original_positions = BTreeSet::new();
    for request in &history.initial.requests {
        if request.request_id.is_empty()
            || !requests.insert(&request.request_id)
            || !valid_position(request.position)
            || request.position.index == 0
            || request.position.index > history.initial.position.index
            || !original_positions.insert(request.position.index)
        {
            return Err("invalid_initial_request".into());
        }
        validate_transaction(&request.intent)?;
    }
    for op in &history.operations {
        if !ids.insert(op.id) || op.node == 0 || op.invocation >= op.response {
            return Err("invalid_operation_identity_or_interval".into());
        }
        match &op.call {
            Call::Write { request_id, intent } => {
                if request_id.is_empty() {
                    return Err("empty_request_identity".into());
                }
                validate_transaction(intent)?;
            }
            Call::Outcome { request_id, intent } => {
                if request_id.is_empty() {
                    return Err("empty_request_identity".into());
                }
                if let Some(intent) = intent {
                    validate_transaction(intent)?;
                }
            }
            Call::Read { minimum, query, .. } => {
                if minimum.is_some_and(|p| !valid_position(p)) {
                    return Err("invalid_minimum_position".into());
                }
                if let Query::Range {
                    start: Some(start),
                    end: Some(end),
                } = query
                    && start > end
                {
                    return Err("reversed_range".into());
                }
            }
        }
        let compatible = match (&op.call, &op.outcome) {
            (Call::Write { .. } | Call::Outcome { .. }, Outcome::Receipt { position, .. }) => {
                valid_position(*position) && position.index > 0
            }
            (Call::Read { .. }, Outcome::Snapshot { position, rows }) => {
                valid_position(*position) && sorted_rows(rows)
            }
            (Call::Outcome { .. }, Outcome::Absent {}) => true,
            (Call::Write { .. }, Outcome::RequestMismatch {})
            | (
                Call::Outcome {
                    intent: Some(_), ..
                },
                Outcome::RequestMismatch {},
            ) => true,
            (_, Outcome::Unknown { reason } | Outcome::DefinitiveAbort { reason }) => {
                !reason.is_empty()
            }
            _ => false,
        };
        if !compatible {
            return Err("incompatible_call_outcome_or_malformed_observation".into());
        }
    }
    let encoded = serde_json::to_vec(history).map_err(|_| "history_encoding".to_owned())?;
    if encoded.len() > MAX_INPUT_BYTES {
        return Err("input_byte_limit".into());
    }
    Ok(())
}

fn validate_transaction(intent: &Transaction) -> Result<(), String> {
    if intent.expected.len() > MAX_FIELDS
        || intent.mutations.is_empty()
        || intent.mutations.len() > MAX_FIELDS
    {
        return Err("transaction_field_limit".into());
    }
    let mut keys = BTreeSet::new();
    if !intent.expected.iter().all(|e| keys.insert(&e.key)) {
        return Err("duplicate_expected_key".into());
    }
    Ok(())
}

fn entries_charge(rows: &Entries) -> usize {
    rows.iter().fold(0usize, |n, (key, value)| {
        n.saturating_add(key.len())
            .saturating_add(value.len())
            .saturating_add(64)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(index: u64) -> Position {
        Position {
            index,
            term: u64::from(index > 0),
        }
    }
    fn t(value: u8) -> Transaction {
        Transaction {
            expected: Vec::new(),
            mutations: vec![Mutation::Put {
                key: b"k".to_vec(),
                value: vec![value],
            }],
        }
    }
    fn conditional(old: Option<u8>, value: u8) -> Transaction {
        let mut intent = t(value);
        intent.expected.push(Expected {
            key: b"k".to_vec(),
            value: old.map(|v| vec![v]),
        });
        intent
    }
    fn write(id: u64, name: &str, start: u64, end: u64, index: u64, value: u8) -> Operation {
        Operation {
            id,
            client: id as u32,
            node: 1 + id % 3,
            invocation: start,
            response: end,
            call: Call::Write {
                request_id: name.into(),
                intent: t(value),
            },
            outcome: Outcome::Receipt {
                position: p(index),
                status: Status::Applied,
                replayed: false,
            },
        }
    }
    fn read(id: u64, start: u64, end: u64, index: u64, value: Option<u8>) -> Operation {
        Operation {
            id,
            client: id as u32,
            node: 1 + id % 3,
            invocation: start,
            response: end,
            call: Call::Read {
                mode: ReadMode::Quorum,
                minimum: None,
                query: Query::Point { key: b"k".to_vec() },
            },
            outcome: Outcome::Snapshot {
                position: p(index),
                rows: value
                    .into_iter()
                    .map(|value| (b"k".to_vec(), vec![value]))
                    .collect(),
            },
        }
    }
    fn h(operations: Vec<Operation>) -> History {
        History {
            schema: 1,
            engine_version: "1.5.0-atlas-test".into(),
            seed: 42,
            history_id: 7,
            profile: "test_controls".into(),
            cluster_id: "cluster-a".into(),
            membership_generation: 0,
            failure_point: None,
            replay_command: "atlas_verify replay history.json".into(),
            initial: InitialState::default(),
            operations,
        }
    }
    fn accept(history: &History) -> Vec<WitnessStep> {
        match check(history, 100_000) {
            CheckResult::Linearizable { witness, .. } => witness,
            result => panic!("expected witness, got {result:?}"),
        }
    }
    fn reject(history: &History) {
        assert!(
            matches!(check(history, 100_000), CheckResult::Violation { .. }),
            "expected violation: {:?}",
            check(history, 100_000)
        );
    }

    #[test]
    fn atomic_multi_key_and_barrier_gaps() {
        let mut w = write(1, "atomic", 1, 2, 5, 8);
        if let Call::Write { intent, .. } = &mut w.call {
            intent.mutations.push(Mutation::Put {
                key: b"z".to_vec(),
                value: vec![9],
            });
        }
        let mut r = read(2, 3, 4, 11, Some(8));
        r.call = Call::Read {
            mode: ReadMode::Quorum,
            minimum: Some(p(5)),
            query: Query::Range {
                start: None,
                end: None,
            },
        };
        r.outcome = Outcome::Snapshot {
            position: p(11),
            rows: vec![(b"k".to_vec(), vec![8]), (b"z".to_vec(), vec![9])],
        };
        accept(&h(vec![w.clone(), r.clone()]));
        if let Outcome::Snapshot { rows, .. } = &mut r.outcome {
            rows.pop();
        }
        reject(&h(vec![w, r]));
    }

    #[test]
    fn real_time_and_lost_acknowledged_commit_are_rejected() {
        reject(&h(vec![write(1, "a", 1, 2, 2, 1), read(2, 3, 4, 3, None)]));
        reject(&h(vec![
            write(1, "a", 1, 2, 5, 1),
            write(2, "b", 3, 4, 3, 2),
        ]));
    }

    #[test]
    fn overlapping_calls_are_searched_not_sorted_by_input_or_node() {
        let history = h(vec![
            read(1, 1, 8, 0, None),
            write(2, "a", 2, 6, 5, 9),
            read(3, 3, 7, 6, Some(9)),
        ]);
        let witness = accept(&history);
        assert_eq!(witness.len(), 3);
        assert_eq!(
            witness.iter().map(|s| s.operation).collect::<Vec<_>>(),
            vec![1, 2, 3]
        );
    }

    #[test]
    fn timeout_can_commit_after_its_response_without_becoming_an_abort() {
        let mut unknown = write(1, "pending", 1, 2, 1, 7);
        unknown.outcome = Outcome::Unknown {
            reason: "transport_timeout".into(),
        };
        let history = h(vec![
            unknown.clone(),
            read(2, 3, 4, 0, None),
            read(3, 5, 6, 2, Some(7)),
        ]);
        let witness = accept(&history);
        assert_eq!(
            witness.iter().map(|s| s.operation).collect::<Vec<_>>(),
            vec![2, 1, 3]
        );
        unknown.outcome = Outcome::DefinitiveAbort {
            reason: "not_submitted".into(),
        };
        reject(&h(vec![unknown, read(2, 3, 4, 2, Some(7))]));
    }

    #[test]
    fn unknown_overwritten_proposal_can_be_omitted() {
        let mut unknown = write(1, "discarded", 1, 2, 1, 8);
        unknown.outcome = Outcome::Unknown {
            reason: "leader_lost".into(),
        };
        let witness = accept(&h(vec![
            unknown,
            write(2, "chosen", 3, 4, 4, 9),
            read(3, 5, 6, 8, Some(9)),
        ]));
        assert_eq!(witness[0].effect, "unknown_omitted");
    }

    #[test]
    fn unknown_original_is_anchored_by_later_named_retry() {
        let mut unknown = write(1, "same", 1, 2, 1, 7);
        unknown.outcome = Outcome::Unknown {
            reason: "lost_ack".into(),
        };
        let mut retry = write(3, "same", 5, 6, 17, 7);
        retry.outcome = Outcome::Receipt {
            position: p(17),
            status: Status::Applied,
            replayed: true,
        };
        let witness = accept(&h(vec![unknown, read(2, 3, 4, 18, Some(7)), retry]));
        assert!(
            witness
                .iter()
                .any(|s| s.effect == "unknown_completed_applied" && s.position == Some(p(17)))
        );
    }

    #[test]
    fn named_retry_cannot_apply_twice_or_change_receipt() {
        let a = write(1, "same", 1, 2, 2, 7);
        let mut retry = write(2, "same", 3, 4, 2, 7);
        retry.outcome = Outcome::Receipt {
            position: p(2),
            status: Status::Applied,
            replayed: true,
        };
        accept(&h(vec![
            a.clone(),
            retry.clone(),
            read(3, 5, 6, 9, Some(7)),
        ]));
        retry.outcome = Outcome::Receipt {
            position: p(3),
            status: Status::Applied,
            replayed: false,
        };
        reject(&h(vec![a.clone(), retry.clone()]));
        retry.outcome = Outcome::Receipt {
            position: p(2),
            status: Status::Applied,
            replayed: false,
        };
        reject(&h(vec![a, retry]));
    }

    #[test]
    fn duplicate_named_conditional_conflict_stays_conflict_after_state_changes() {
        let mut conflict = write(1, "conflict", 1, 2, 2, 8);
        conflict.call = Call::Write {
            request_id: "conflict".into(),
            intent: conditional(Some(7), 8),
        };
        conflict.outcome = Outcome::Receipt {
            position: p(2),
            status: Status::Conflict,
            replayed: false,
        };
        let mut retry = conflict.clone();
        retry.id = 3;
        retry.invocation = 5;
        retry.response = 6;
        retry.outcome = Outcome::Receipt {
            position: p(2),
            status: Status::Conflict,
            replayed: true,
        };
        accept(&h(vec![
            conflict.clone(),
            write(2, "make-condition-true", 3, 4, 5, 7),
            retry.clone(),
            read(4, 7, 8, 9, Some(7)),
        ]));
        retry.outcome = Outcome::Receipt {
            position: p(2),
            status: Status::Applied,
            replayed: true,
        };
        reject(&h(vec![
            conflict,
            write(2, "make-condition-true", 3, 4, 5, 7),
            retry,
        ]));
    }

    #[test]
    fn conditional_writes_must_choose_exactly_one_winner() {
        let mut a = write(1, "a", 1, 5, 2, 1);
        let mut b = write(2, "b", 2, 6, 3, 2);
        a.call = Call::Write {
            request_id: "a".into(),
            intent: conditional(None, 1),
        };
        b.call = Call::Write {
            request_id: "b".into(),
            intent: conditional(None, 2),
        };
        reject(&h(vec![a.clone(), b.clone()]));
        b.outcome = Outcome::Receipt {
            position: p(3),
            status: Status::Conflict,
            replayed: false,
        };
        accept(&h(vec![a, b, read(3, 7, 8, 4, Some(1))]));
    }

    #[test]
    fn false_conflict_and_partial_conflict_mutation_are_rejected() {
        let mut false_conflict = write(1, "a", 1, 2, 2, 8);
        false_conflict.call = Call::Write {
            request_id: "a".into(),
            intent: conditional(None, 8),
        };
        false_conflict.outcome = Outcome::Receipt {
            position: p(2),
            status: Status::Conflict,
            replayed: false,
        };
        reject(&h(vec![false_conflict.clone()]));
        if let Call::Write { intent, .. } = &mut false_conflict.call {
            intent.expected[0].value = Some(vec![7]);
        }
        reject(&h(vec![false_conflict, read(2, 3, 4, 5, Some(8))]));
    }

    #[test]
    fn stale_local_prefix_is_allowed_but_quorum_stale_read_is_not() {
        let a = write(1, "a", 1, 2, 2, 7);
        let mut stale = read(2, 3, 4, 0, None);
        reject(&h(vec![a.clone(), stale.clone()]));
        if let Call::Read { mode, .. } = &mut stale.call {
            *mode = ReadMode::Local;
        }
        match check(&h(vec![a.clone(), stale.clone()]), 1000) {
            CheckResult::Linearizable {
                local_prefix_reads, ..
            } => assert_eq!(local_prefix_reads, 1),
            other => panic!("{other:?}"),
        }
        stale.outcome = Outcome::Snapshot {
            position: p(0),
            rows: vec![(b"k".to_vec(), vec![7])],
        };
        reject(&h(vec![a, stale]));
    }

    #[test]
    fn local_reads_cannot_predict_future_invocations_and_enforce_minimum() {
        let mut local = read(1, 1, 2, 5, Some(7));
        if let Call::Read { mode, .. } = &mut local.call {
            *mode = ReadMode::Local;
        }
        reject(&h(vec![local, write(2, "future", 3, 4, 4, 7)]));
        let mut local = read(2, 3, 4, 0, None);
        if let Call::Read { mode, minimum, .. } = &mut local.call {
            *mode = ReadMode::Local;
            *minimum = Some(p(2));
        }
        reject(&h(vec![write(1, "a", 1, 2, 2, 7), local]));
    }

    #[test]
    fn outcome_absence_and_identity_mismatch_are_state_observations() {
        let a = write(1, "a", 1, 2, 2, 7);
        let lookup = Operation {
            id: 2,
            client: 0,
            node: 2,
            invocation: 3,
            response: 4,
            call: Call::Outcome {
                request_id: "a".into(),
                intent: None,
            },
            outcome: Outcome::Absent {},
        };
        reject(&h(vec![a.clone(), lookup.clone()]));
        let mut found = lookup.clone();
        found.outcome = Outcome::Receipt {
            position: p(2),
            status: Status::Applied,
            replayed: false,
        };
        accept(&h(vec![a.clone(), found]));
        let mut mismatch = lookup;
        mismatch.call = Call::Write {
            request_id: "a".into(),
            intent: t(9),
        };
        mismatch.outcome = Outcome::RequestMismatch {};
        accept(&h(vec![a.clone(), mismatch.clone()]));
        mismatch.call = Call::Write {
            request_id: "a".into(),
            intent: t(7),
        };
        reject(&h(vec![a, mismatch]));
    }

    #[test]
    fn unknown_term_uses_observed_anchor_and_rejects_split_brain_positions() {
        let mut u = write(1, "u", 1, 2, 1, 7);
        u.outcome = Outcome::Unknown {
            reason: "lost_ack".into(),
        };
        let mut r = read(2, 3, 4, 1, Some(7));
        r.outcome = Outcome::Snapshot {
            position: Position { index: 1, term: 4 },
            rows: vec![(b"k".to_vec(), vec![7])],
        };
        accept(&h(vec![u, r]));
        reject(&h(vec![
            write(1, "a", 1, 6, 3, 7),
            write(2, "b", 2, 5, 3, 9),
        ]));
    }

    #[test]
    fn binary_range_order_duplicates_and_repeated_mutations() {
        let mut w = write(1, "a", 1, 2, 2, 1);
        if let Call::Write { intent, .. } = &mut w.call {
            intent.mutations = vec![
                Mutation::Put {
                    key: vec![0],
                    value: vec![1],
                },
                Mutation::Put {
                    key: vec![255],
                    value: vec![2],
                },
                Mutation::Delete { key: vec![0] },
                Mutation::Put {
                    key: vec![0],
                    value: vec![3],
                },
            ];
        }
        let mut r = read(2, 3, 4, 3, None);
        r.call = Call::Read {
            mode: ReadMode::Quorum,
            minimum: None,
            query: Query::Range {
                start: Some(vec![0]),
                end: Some(vec![255]),
            },
        };
        r.outcome = Outcome::Snapshot {
            position: p(3),
            rows: vec![(vec![0], vec![3])],
        };
        accept(&h(vec![w.clone(), r.clone()]));
        if let Outcome::Snapshot { rows, .. } = &mut r.outcome {
            rows.push(rows[0].clone());
        }
        assert!(matches!(
            check(&h(vec![w, r]), 100),
            CheckResult::Invalid { .. }
        ));
    }

    #[test]
    fn limits_and_invalid_are_never_reported_as_violations_or_witnesses() {
        let history = h(vec![write(1, "a", 1, 2, 2, 7), read(2, 3, 4, 3, Some(7))]);
        assert!(matches!(
            check(&history, 1),
            CheckResult::Inconclusive { .. }
        ));
        assert!(matches!(check(&history, 0), CheckResult::Invalid { .. }));
        let mut invalid = history.clone();
        invalid.operations[1].id = 1;
        assert!(matches!(check(&invalid, 100), CheckResult::Invalid { .. }));
        let mut invalid = history;
        invalid.operations[0].response = 0;
        assert!(matches!(check(&invalid, 100), CheckResult::Invalid { .. }));
    }

    #[test]
    fn schema_round_trip_preserves_real_observations_and_replay_metadata() {
        let history = h(vec![write(1, "a", 1, 2, 5, 7), read(2, 3, 4, 8, Some(7))]);
        let json = serde_json::to_vec(&history).unwrap();
        let replay: History = serde_json::from_slice(&json).unwrap();
        assert_eq!(history, replay);
        assert_eq!(check(&history, 1000), check(&replay, 1000));
    }

    #[test]
    fn reducer_preserves_mutation_context_and_never_claims_global_minimum() {
        let history = h(vec![
            write(1, "a", 1, 2, 2, 7),
            read(2, 3, 4, 3, Some(7)),
            read(3, 5, 6, 4, None),
        ]);
        let reduction = minimize(&history, 1000, 100);
        assert!(reduction.context_preserving_one_minimal);
        assert!(matches!(reduction.result, CheckResult::Violation { .. }));
        assert_eq!(reduction.history.operations[0], history.operations[0]);
        assert_eq!(reduction.history.initial, history.initial);
        assert_eq!(
            reduction
                .history
                .operations
                .iter()
                .map(|op| op.id)
                .collect::<Vec<_>>(),
            vec![1, 3]
        );
        assert!(!minimize(&history, 1000, 0).context_preserving_one_minimal);
        assert!(!minimize(&h(vec![]), 1000, 100).context_preserving_one_minimal);
    }

    #[test]
    fn concurrent_named_duplicates_have_one_original_and_one_replay() {
        let original = write(1, "same", 1, 8, 4, 7);
        let mut duplicate = write(2, "same", 2, 7, 4, 7);
        duplicate.outcome = Outcome::Receipt {
            position: p(4),
            status: Status::Applied,
            replayed: true,
        };
        // Input order is deliberately the opposite of the valid witness.
        let witness = accept(&h(vec![duplicate.clone(), original.clone()]));
        assert_eq!(
            witness.iter().map(|s| s.operation).collect::<Vec<_>>(),
            vec![1, 2]
        );
        duplicate.outcome = Outcome::Receipt {
            position: p(4),
            status: Status::Applied,
            replayed: false,
        };
        reject(&h(vec![original, duplicate]));
    }

    #[test]
    fn hard_operation_and_model_memory_limits_are_distinct() {
        let mut operations = Vec::new();
        for id in 0..64 {
            let mut op = write(id, "unsubmitted", 2 * id + 1, 2 * id + 2, 1, 7);
            op.outcome = Outcome::DefinitiveAbort {
                reason: "admission_rejected".into(),
            };
            operations.push(op);
        }
        accept(&h(operations.clone()));
        let mut extra = operations[0].clone();
        extra.id = 99;
        operations.push(extra);
        assert!(matches!(
            check(&h(operations), 1000),
            CheckResult::Invalid { .. }
        ));
        let mut enormous = write(1, "big", 1, 2, 1, 7);
        if let Call::Write { intent, .. } = &mut enormous.call {
            intent.mutations = vec![Mutation::Put {
                key: b"k".to_vec(),
                value: vec![0; MAX_MODEL_BYTES],
            }];
        }
        assert!(matches!(
            check(&h(vec![enormous]), 100),
            CheckResult::Inconclusive { .. }
        ));
    }

    #[test]
    fn unknown_future_fields_are_rejected_instead_of_silently_dropped() {
        let mut encoded = serde_json::to_value(h(vec![read(1, 1, 2, 0, None)])).unwrap();
        encoded["operations"][0]["outcome"]["unsupported_observation"] = true.into();
        assert!(serde_json::from_value::<History>(encoded).is_err());
    }

    #[test]
    fn exhaustive_tiny_register_oracle_agrees_on_6144_synthetic_histories() {
        // Deliberately separate scalar implementation and six explicit orders.
        // These are checker selftests, not measured cluster campaign histories.
        const ORDERS: [[usize; 3]; 6] = [
            [0, 1, 2],
            [0, 2, 1],
            [1, 0, 2],
            [1, 2, 0],
            [2, 0, 1],
            [2, 1, 0],
        ];
        fn oracle(ops: &[Operation], order: &[usize; 3], local: bool) -> bool {
            let mut rank = [0; 3];
            for (n, &slot) in order.iter().enumerate() {
                rank[slot] = n;
            }
            for a in 0..3 {
                for b in 0..3 {
                    if local && b == 2 {
                        continue;
                    }
                    if ops[a].response < ops[b].invocation && rank[a] > rank[b] {
                        return false;
                    }
                }
            }
            let mut scalar = None;
            let mut index = 0;
            for &slot in order {
                if slot < 2 {
                    let Outcome::Receipt { position, .. } = ops[slot].outcome else {
                        unreachable!()
                    };
                    if position.index <= index {
                        return false;
                    }
                    index = position.index;
                    scalar = Some(slot as u8 + 1);
                } else {
                    let Outcome::Snapshot { position, ref rows } = ops[slot].outcome else {
                        unreachable!()
                    };
                    let value = rows.first().map(|(_, value)| value[0]);
                    if position.index < index || value != scalar {
                        return false;
                    }
                    index = position.index;
                }
            }
            true
        }
        let intervals = [(1, 2), (2, 5), (3, 4), (5, 6)];
        let mut count = 0;
        for &(a_start, a_end) in &intervals {
            for &(b_start, b_end) in &intervals {
                for &(r_start, r_end) in &intervals {
                    for (a_position, b_position) in [(1, 2), (2, 1), (1, 1)] {
                        for r_position in 0..4 {
                            for value in [None, Some(1), Some(2), Some(9)] {
                                for local in [false, true] {
                                    let mut ops = vec![
                                        write(1, "a", a_start, a_end, a_position, 1),
                                        write(2, "b", b_start, b_end, b_position, 2),
                                        read(3, r_start, r_end, r_position, value),
                                    ];
                                    if local && let Call::Read { mode, .. } = &mut ops[2].call {
                                        *mode = ReadMode::Local;
                                    }
                                    let expected =
                                        ORDERS.iter().any(|order| oracle(&ops, order, local));
                                    let actual = check(&h(ops), 1000);
                                    assert_eq!(actual.is_linearizable(), expected, "{actual:?}");
                                    assert!(!matches!(
                                        actual,
                                        CheckResult::Invalid { .. }
                                            | CheckResult::Inconclusive { .. }
                                    ));
                                    count += 1;
                                }
                            }
                        }
                    }
                }
            }
        }
        assert_eq!(count, 6144);
    }

    #[test]
    fn independent_pending_oracle_agrees_on_12288_ambiguous_traces() {
        const ORDERS: [[usize; 3]; 6] = [
            [0, 1, 2],
            [0, 2, 1],
            [1, 0, 2],
            [1, 2, 0],
            [2, 0, 1],
            [2, 1, 0],
        ];
        // Unknown conditional write: k absent -> 7. Known conditional write:
        // k absent -> 8. Enumerate pending omission and every relevant concrete
        // completion index, rather than copying the checker's greedy choice.
        fn oracle(ops: &[Operation], local: bool) -> bool {
            for order in ORDERS {
                let mut rank = [0; 3];
                for (n, slot) in order.iter().copied().enumerate() {
                    rank[slot] = n;
                }
                if (0..3).any(|a| {
                    (0..3).any(|b| {
                        a != 0
                            && !(local && b == 2)
                            && ops[a].response < ops[b].invocation
                            && rank[a] > rank[b]
                    })
                }) {
                    continue;
                }
                // Index 0 means omitted. Index 5 represents all completions
                // strictly after the maximum observed position 3.
                for unknown_position in 0..=5 {
                    let mut scalar = None;
                    let mut head = 0;
                    let mut valid = true;
                    for slot in order {
                        match slot {
                            0 if unknown_position == 0 => {}
                            0 => {
                                if unknown_position <= head {
                                    valid = false;
                                    break;
                                }
                                head = unknown_position;
                                if scalar.is_none() {
                                    scalar = Some(7);
                                }
                            }
                            1 => {
                                let Outcome::Receipt {
                                    position, status, ..
                                } = ops[1].outcome
                                else {
                                    unreachable!()
                                };
                                let matches = scalar.is_none();
                                if position.index <= head || (status == Status::Applied) != matches
                                {
                                    valid = false;
                                    break;
                                }
                                head = position.index;
                                if matches {
                                    scalar = Some(8);
                                }
                            }
                            2 => {
                                let Outcome::Snapshot { position, ref rows } = ops[2].outcome
                                else {
                                    unreachable!()
                                };
                                if position.index < head
                                    || rows.first().map(|(_, v)| v[0]) != scalar
                                {
                                    valid = false;
                                    break;
                                }
                                head = position.index;
                            }
                            _ => unreachable!(),
                        }
                    }
                    if valid {
                        return true;
                    }
                }
            }
            false
        }
        let intervals = [(1, 2), (2, 5), (3, 4), (5, 6)];
        let mut count = 0;
        for &(u_start, u_end) in &intervals {
            for &(b_start, b_end) in &intervals {
                for &(r_start, r_end) in &intervals {
                    for b_position in 1..=3 {
                        for r_position in 0..4 {
                            for value in [None, Some(7), Some(8), Some(9)] {
                                for local in [false, true] {
                                    for status in [Status::Applied, Status::Conflict] {
                                        let mut u = write(1, "pending", u_start, u_end, 1, 7);
                                        u.call = Call::Write {
                                            request_id: "pending".into(),
                                            intent: conditional(None, 7),
                                        };
                                        u.outcome = Outcome::Unknown {
                                            reason: "timeout".into(),
                                        };
                                        let mut b =
                                            write(2, "known", b_start, b_end, b_position, 8);
                                        b.call = Call::Write {
                                            request_id: "known".into(),
                                            intent: conditional(None, 8),
                                        };
                                        b.outcome = Outcome::Receipt {
                                            position: p(b_position),
                                            status,
                                            replayed: false,
                                        };
                                        let mut r = read(3, r_start, r_end, r_position, value);
                                        if local && let Call::Read { mode, .. } = &mut r.call {
                                            *mode = ReadMode::Local;
                                        }
                                        let ops = vec![u, b, r];
                                        let expected = oracle(&ops, local);
                                        let actual = check(&h(ops), 1000);
                                        assert_eq!(
                                            actual.is_linearizable(),
                                            expected,
                                            "{actual:?}"
                                        );
                                        assert!(!matches!(
                                            actual,
                                            CheckResult::Invalid { .. }
                                                | CheckResult::Inconclusive { .. }
                                        ));
                                        count += 1;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        assert_eq!(count, 12288);
    }
}

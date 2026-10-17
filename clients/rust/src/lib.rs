//! Bounded synchronous client for the local Polybase HTTP API. No automatic write retry.
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    time::Duration,
};

#[derive(Debug)]
pub enum Error {
    Io(std::io::Error),
    Json(serde_json::Error),
    Protocol(&'static str),
    Api { status: u16, body: Value },
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for Error {}
impl From<std::io::Error> for Error {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e)
    }
}
impl From<serde_json::Error> for Error {
    fn from(e: serde_json::Error) -> Self {
        Self::Json(e)
    }
}
pub type Result<T> = std::result::Result<T, Error>;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Query {
    pub key_prefix: String,
    pub predicate: String,
    pub value: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub json: Option<Value>,
}
impl Query {
    pub fn all(prefix: &[u8]) -> Self {
        Self {
            key_prefix: hex(prefix),
            predicate: "any".into(),
            value: String::new(),
            json: None,
        }
    }
    pub fn json(prefix: &[u8], predicate: Value) -> Self {
        Self {
            key_prefix: hex(prefix),
            predicate: "json".into(),
            value: String::new(),
            json: Some(predicate),
        }
    }
}
#[derive(Clone, Debug, Deserialize)]
pub struct Row {
    pub key: String,
    pub value: String,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Page {
    pub position: String,
    pub rows: Vec<Row>,
    pub next: Option<String>,
    pub explain: Value,
}
#[derive(Clone, Debug, Deserialize)]
pub struct RevisionRead {
    pub value: Option<String>,
    pub revision: String,
    pub position: String,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Receipt {
    pub position: String,
    pub wrote: bool,
    pub durable: bool,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Session {
    pub id: String,
    pub instance: String,
    pub token: String,
    pub position: String,
    pub rows: Vec<Row>,
}
/// A resumed subscription has an identity but does not return another snapshot.
#[derive(Clone, Debug, Deserialize)]
pub struct ResumedSession {
    pub id: String,
    pub instance: String,
}

pub trait SessionIdentity {
    fn id(&self) -> &str;
    fn instance(&self) -> &str;
}
impl SessionIdentity for Session {
    fn id(&self) -> &str {
        &self.id
    }
    fn instance(&self) -> &str {
        &self.instance
    }
}
impl SessionIdentity for ResumedSession {
    fn id(&self) -> &str {
        &self.id
    }
    fn instance(&self) -> &str {
        &self.instance
    }
}

/// One bounded current-head search; this does not register a subscription.
#[derive(Clone, Debug, Serialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum SearchQuery {
    Json {
        key_prefix: String,
        path: Vec<String>,
        value: Value,
    },
    Text {
        key_prefix: String,
        text: String,
    },
}

#[derive(Clone, Debug, Deserialize)]
pub struct SearchResult {
    pub position: String,
    pub indexed: bool,
    pub rows: Vec<Row>,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Change {
    pub key: String,
    pub before: Option<String>,
    pub after: Option<String>,
}
#[derive(Clone, Debug, Deserialize)]
pub struct Commit {
    pub position: String,
    pub changes: Vec<Change>,
}
#[derive(Clone, Debug, Deserialize)]
pub struct StreamPage {
    pub commits: Vec<Commit>,
    pub token: String,
    pub position: String,
    pub head: String,
    pub floor: String,
}

#[derive(Clone)]
pub struct Client {
    address: SocketAddr,
}
impl Client {
    pub fn new(address: SocketAddr) -> Result<Self> {
        if !address.is_ipv4() || !address.ip().is_loopback() || address.port() == 0 {
            return Err(Error::Protocol(
                "only IPv4 loopback endpoints are supported",
            ));
        }
        Ok(Self { address })
    }
    /// A transport error after sending a write leaves its outcome uncertain.
    pub fn call<T: DeserializeOwned>(&self, route: &str, body: &impl Serialize) -> Result<T> {
        if !route.bytes().all(|b| b.is_ascii_lowercase() || b == b'-') {
            return Err(Error::Protocol("invalid route"));
        }
        let body = serde_json::to_vec(body)?;
        if body.len() > 128 * 1024 {
            return Err(Error::Protocol("request exceeds 128 KiB"));
        }
        let mut socket = TcpStream::connect_timeout(&self.address, Duration::from_secs(5))?;
        socket.set_read_timeout(Some(Duration::from_secs(5)))?;
        socket.set_write_timeout(Some(Duration::from_secs(5)))?;
        write!(
            socket,
            "POST /api/{route} HTTP/1.1\r\nHost: {}\r\nOrigin: http://{}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            self.address,
            self.address,
            body.len()
        )?;
        socket.write_all(&body)?;
        let mut response = Vec::new();
        socket
            .take(8 * 1024 * 1024 + 8193)
            .read_to_end(&mut response)?;
        if response.len() > 8 * 1024 * 1024 + 8192 {
            return Err(Error::Protocol("response exceeds bound"));
        }
        let end = response
            .windows(4)
            .position(|w| w == b"\r\n\r\n")
            .ok_or(Error::Protocol("missing HTTP header"))?;
        let header = std::str::from_utf8(&response[..end])
            .map_err(|_| Error::Protocol("invalid HTTP header"))?;
        let status = header
            .lines()
            .next()
            .and_then(|s| s.strip_prefix("HTTP/1.1 "))
            .and_then(|s| s.split(' ').next())
            .and_then(|s| s.parse::<u16>().ok())
            .ok_or(Error::Protocol("invalid HTTP status"))?;
        let payload = &response[end + 4..];
        let length = header.lines().find_map(|s| {
            s.to_ascii_lowercase()
                .strip_prefix("content-length:")
                .and_then(|s| s.trim().parse::<usize>().ok())
        });
        if length != Some(payload.len()) {
            return Err(Error::Protocol("incomplete HTTP response"));
        }
        if status != 200 {
            return Err(Error::Api {
                status,
                body: serde_json::from_slice(payload).unwrap_or_else(|_| {
                    Value::String(String::from_utf8_lossy(payload).into_owned())
                }),
            });
        }
        Ok(serde_json::from_slice(payload)?)
    }
    pub fn page(&self, query: &Query, cursor: Option<&str>, limit: usize) -> Result<Page> {
        self.page_with_scan(query, cursor, limit, false)
    }
    pub fn page_with_scan(
        &self,
        query: &Query,
        cursor: Option<&str>,
        limit: usize,
        force_scan: bool,
    ) -> Result<Page> {
        let mut body = json!({"query":query,"cursor":cursor,"limit":limit});
        if force_scan {
            body["force_scan"] = json!(true);
        }
        self.call("query-page", &body)
    }
    pub fn read_revision(&self, key: &[u8]) -> Result<RevisionRead> {
        self.call("read-revision", &json!({"key":hex(key)}))
    }
    pub fn write_revision(&self, revision: &str, value: Option<&[u8]>) -> Result<Receipt> {
        self.call(
            "write-revision",
            &json!({"revision":revision,"value":value.map(hex)}),
        )
    }
    pub fn subscribe(&self, query: &Query) -> Result<Session> {
        self.call("query", query)
    }
    pub fn resume(&self, token: &str) -> Result<ResumedSession> {
        self.call("resume", &json!({"token":token}))
    }
    /// Supply the last *applied* token; persist rows and this token atomically in the application.
    pub fn poll(&self, session: &impl SessionIdentity, applied_token: &str) -> Result<StreamPage> {
        self.call(
            "poll",
            &json!({"id":session.id(),"instance":session.instance(),"token":applied_token}),
        )
    }
    pub fn unsubscribe(&self, session: &impl SessionIdentity, token: &str) -> Result<Value> {
        self.call(
            "unsubscribe",
            &json!({"id":session.id(),"instance":session.instance(),"token":token}),
        )
    }
    pub fn snapshot_at(&self, position: u64) -> Result<Value> {
        self.call("snapshot-at", &json!({"position":position.to_string()}))
    }
    pub fn backup(&self, directory: &str) -> Result<Value> {
        self.call("backup", &json!({"directory":directory}))
    }
    pub fn verify_backup(&self, directory: &str) -> Result<Value> {
        self.call("verify-backup", &json!({"directory":directory}))
    }
    /// This route takes prefix bytes as a JSON array, unlike hex key_prefix fields.
    pub fn create_index(&self, name: &str, prefix: &[u8], path: &[&str]) -> Result<Value> {
        self.call(
            "index-create",
            &json!({"name":name,"prefix":prefix,"path":path}),
        )
    }
    pub fn indexes(&self) -> Result<Value> {
        self.call("index-list", &json!({}))
    }
    pub fn search_index(&self, name: &str, value: Value) -> Result<SearchResult> {
        self.call("index-search", &json!({"name":name,"value":value}))
    }
    pub fn drop_index(&self, name: &str) -> Result<Value> {
        self.call("index-drop", &json!({"name":name}))
    }
    pub fn compaction_advice(&self, retain_commits: u64) -> Result<Value> {
        self.call(
            "compaction-advice",
            &json!({"retain_commits":retain_commits.to_string()}),
        )
    }
    pub fn search(&self, query: &SearchQuery) -> Result<SearchResult> {
        self.call("search", query)
    }
}
pub fn hex(bytes: &[u8]) -> String {
    use std::fmt::Write;
    bytes
        .iter()
        .fold(String::with_capacity(bytes.len() * 2), |mut s, b| {
            write!(s, "{b:02x}").expect("String write");
            s
        })
}
pub fn unhex(s: &str) -> Result<Vec<u8>> {
    if !s.len().is_multiple_of(2)
        || !s
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return Err(Error::Protocol("invalid hex"));
    }
    s.as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|b| {
            u8::from_str_radix(std::str::from_utf8(b).expect("ASCII"), 16)
                .map_err(|_| Error::Protocol("invalid hex"))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{BufRead, BufReader},
        net::TcpListener,
        thread,
    };

    fn response(status: u16, body: &[u8]) -> Result<Value> {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let body = body.to_vec();
        let worker = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let mut reader = BufReader::new(&mut socket);
            let mut length = 0;
            loop {
                let mut line = String::new();
                assert!(reader.read_line(&mut line).unwrap() > 0);
                if line == "\r\n" {
                    break;
                }
                if let Some(value) = line.to_ascii_lowercase().strip_prefix("content-length:") {
                    length = value.trim().parse::<usize>().unwrap();
                }
            }
            assert!(length <= 128 * 1024);
            reader.read_exact(&mut vec![0; length]).unwrap();
            write!(
                reader.get_mut(),
                "HTTP/1.1 {status} Test\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                body.len()
            )
            .unwrap();
            reader.get_mut().write_all(&body).unwrap();
        });
        let result = Client::new(address)
            .unwrap()
            .call("read", &json!({"key":""}));
        worker.join().unwrap();
        result
    }

    #[test]
    fn non_json_errors_keep_status_and_text_while_success_requires_json() {
        for (status, bytes, text) in [
            (500, b"upstream panic".as_slice(), "upstream panic"),
            (503, b"".as_slice(), ""),
            (502, b"bad \xff".as_slice(), "bad \u{fffd}"),
        ] {
            assert!(
                matches!(response(status, bytes), Err(Error::Api { status: actual, body }) if actual == status && body == json!(text))
            );
        }
        assert!(
            matches!(response(409, br#"{"error":"conflict"}"#), Err(Error::Api { status: 409, body }) if body == json!({"error":"conflict"}))
        );
        assert!(matches!(
            response(200, b"invalid success"),
            Err(Error::Json(_))
        ));
    }
}

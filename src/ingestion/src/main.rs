//! Stateless, highly-concurrent log receiver.
//!
//! Accepts batches of raw log lines over HTTP and writes them straight to Kafka,
//! partitioned by source key so a host/service keeps ordering. Being stateless,
//! it scales horizontally behind a load balancer and is the throughput front door
//! for the pipeline (the Python inference workers consume the Kafka partitions).

use actix_web::{post, web, App, HttpResponse, HttpServer, Responder};
use rdkafka::config::ClientConfig;
use rdkafka::producer::{FutureProducer, FutureRecord};
use serde::Deserialize;
use std::time::Duration;

#[derive(Deserialize)]
struct IngestBatch {
    source: String,
    lines: Vec<String>,
}

struct AppState {
    producer: FutureProducer,
    topic: String,
}

#[post("/ingest")]
async fn ingest(state: web::Data<AppState>, body: web::Json<IngestBatch>) -> impl Responder {
    let mut accepted = 0usize;
    for line in &body.lines {
        let payload = serde_json::json!({ "line": line, "source": body.source }).to_string();
        let record = FutureRecord::to(&state.topic)
            .key(&body.source)
            .payload(&payload);
        if state
            .producer
            .send(record, Duration::from_secs(0))
            .await
            .is_ok()
        {
            accepted += 1;
        }
    }
    HttpResponse::Ok().json(serde_json::json!({ "accepted": accepted }))
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    let brokers = std::env::var("KAFKA_BROKERS").unwrap_or_else(|_| "localhost:9092".into());
    let topic = std::env::var("LOGSHIELD_TOPIC").unwrap_or_else(|_| "logs.raw".into());

    let producer: FutureProducer = ClientConfig::new()
        .set("bootstrap.servers", &brokers)
        .set("queue.buffering.max.messages", "1000000")
        .set("compression.type", "lz4")
        .set("linger.ms", "5")
        .create()
        .expect("kafka producer creation failed");

    let state = web::Data::new(AppState { producer, topic });
    println!("logshield receiver listening on 0.0.0.0:8080 -> kafka {brokers}");
    HttpServer::new(move || App::new().app_data(state.clone()).service(ingest))
        .workers(num_cpus_or(4))
        .bind(("0.0.0.0", 8080))?
        .run()
        .await
}

fn num_cpus_or(default: usize) -> usize {
    std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(default)
}

//! Run one (reader, shape) Avro measurement - the Rust counterpart of avro_one.py.
//!
//!     avro_rust <reader> <shape> <file.avro> <reps> [batch_size] [utf8_view]
//!
//! Prints one JSON line: best/median wall time in ms and the row count. Called by
//! measure_avro_rust.py; not intended for direct use.
//!
//! Every reader decodes the same in-memory bytes; reading the file is outside the
//! timing. One thread throughout (neither crate parallelises a single file).
//!
//!   arrow-avro    arrow_avro::reader::Reader -> Arrow RecordBatches (columnar; the
//!                 counterpart of rugo's Morsels). batch_size defaults to the
//!                 crate's 1024; utf8_view=1 decodes strings to StringViewArray.
//!   apache-avro   apache_avro::Reader -> one Value per record (row-oriented)
//!
//! Shapes: `all` reads every field; `narrow` reads id, amount and country.
//! arrow-avro is given a projection (pruned reader schema); apache-avro is given a
//! reader schema of just those fields, which is how it skips the rest.

use std::io::Cursor;
use std::time::Instant;

const NARROW: [&str; 3] = ["id", "amount", "country"];

fn writer_schema_json(data: &[u8]) -> serde_json::Value {
    let reader = apache_avro::Reader::new(Cursor::new(data)).expect("open avro");
    serde_json::from_str(&reader.writer_schema().canonical_form()).expect("schema json")
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 5 {
        eprintln!("usage: avro_rust <reader> <shape> <file.avro> <reps> [batch_size] [utf8_view]");
        std::process::exit(2);
    }
    let (reader, shape, path) = (args[1].as_str(), args[2].as_str(), &args[3]);
    let reps: usize = args[4].parse().expect("reps");
    let batch_size: usize = args.get(5).map(|s| s.parse().expect("batch_size")).unwrap_or(1024);
    let utf8_view = args.get(6).map(|s| s == "1").unwrap_or(false);
    let narrow = match shape {
        "all" => false,
        "narrow" => true,
        _ => panic!("unknown shape {shape}"),
    };
    let data = std::fs::read(path).expect("read file");

    // Top-level field indexes / pruned schema for the narrow shape.
    let schema = writer_schema_json(&data);
    let fields = schema["fields"].as_array().expect("record fields");
    let projection: Vec<usize> = NARROW
        .iter()
        .map(|n| fields.iter().position(|f| f["name"] == *n).expect("narrow field"))
        .collect();
    let mut pruned = schema.clone();
    pruned["fields"] = serde_json::Value::Array(projection.iter().map(|&i| fields[i].clone()).collect());
    let apache_reader_schema = apache_avro::Schema::parse_str(&pruned.to_string()).expect("reader schema");

    let go = || -> usize {
        match reader {
            "arrow-avro" => {
                let mut b = arrow_avro::reader::ReaderBuilder::new()
                    .with_batch_size(batch_size)
                    .with_utf8_view(utf8_view);
                if narrow {
                    b = b.with_projection(projection.clone());
                }
                let r = b.build(Cursor::new(&data[..])).expect("arrow-avro reader");
                r.map(|batch| batch.expect("arrow-avro batch").num_rows()).sum()
            }
            "apache-avro" => {
                let r = if narrow {
                    apache_avro::Reader::builder(Cursor::new(&data[..]))
                        .reader_schema(&apache_reader_schema)
                        .build()
                } else {
                    apache_avro::Reader::new(Cursor::new(&data[..]))
                }
                .expect("apache-avro reader");
                r.map(|v| {
                    v.expect("apache-avro record");
                    1usize
                })
                .sum()
            }
            _ => panic!("unknown reader {reader}"),
        }
    };

    let mut times = Vec::with_capacity(reps);
    let mut rows = 0;
    for _ in 0..reps {
        let t = Instant::now();
        rows = std::hint::black_box(go());
        times.push(t.elapsed().as_secs_f64() * 1000.0);
    }
    let best = times.iter().cloned().fold(f64::INFINITY, f64::min);
    let mut sorted = times.clone();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let median = if reps % 2 == 1 {
        sorted[reps / 2]
    } else {
        (sorted[reps / 2 - 1] + sorted[reps / 2]) / 2.0
    };
    println!(
        "{{\"best_ms\": {:.1}, \"median_ms\": {:.1}, \"rows\": {}}}",
        best, median, rows
    );
}

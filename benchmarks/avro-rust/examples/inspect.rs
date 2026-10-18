//! Print arrow-avro's output schema and row 0 of the first batch, for checking
//! that it decodes gen_avro.py's file to the same values as rugo/fastavro.
//!
//!     cargo run --release --example inspect -- <file.avro>

use std::io::Cursor;

fn main() {
    let path = std::env::args().nth(1).expect("usage: inspect <file.avro>");
    let data = std::fs::read(path).expect("read file");
    let mut r = arrow_avro::reader::ReaderBuilder::new()
        .build(Cursor::new(&data[..]))
        .expect("arrow-avro reader");
    let batch = r.next().expect("a batch").expect("decode");
    for (field, col) in batch.schema().fields().iter().zip(batch.columns()) {
        println!("{} {:?}\n    {:?}", field.name(), field.data_type(), col.slice(0, 1));
    }
}

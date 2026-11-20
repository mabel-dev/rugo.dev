// Per-domain content for the standalone viewer sites. Each site serves the same viewer
// (Parquet, Avro and ORC) under a landing page written for the format people search for.
// Edit the copy here; tools/build_sites.mjs turns it into build/sites/<domain>/.

export const sites = [
  {
    domain: "avroviewer.com",
    format: "Avro",
    ext: ".avro",
    title: "Avro viewer online: open .avro files in your browser",
    h1: "Avro file viewer",
    description:
      "Open an .avro file in your browser and see its schema, record count and records. No install, no account, and your file never leaves your machine.",
    lead:
      "Open an .avro file and see its schema, how many records it holds and the records themselves, with no install and no account.",
    sibling: { domain: "orcviewer.com", label: "ORC viewer" },
    cards: [
      {
        h: "The schema, as a tree",
        p: "Records, arrays, maps, unions, enums and logical types such as dates and decimals, laid out so a nested schema is readable at a glance.",
      },
      {
        h: "Records, block by block",
        p: "Step through the file's blocks and read the records in each. Null, deflate and snappy blocks all open. Counting every record and checking every block's sync marker runs alongside, with progress and a cancel button.",
      },
      {
        h: "Header and health",
        p: "The codec, the record name, the header metadata, and a validation pass over the header, the schema and each block's sync marker, so a corrupt or cut-off file tells you where it breaks.",
      },
    ],
    faq: [
      {
        q: "How do I open an Avro file without installing anything?",
        a: "Drop the .avro file on the viewer above, choose it with the file picker, or paste a URL. The viewer reads the header for the schema, then opens the first block of records straight away.",
      },
      {
        q: "Is my Avro file uploaded anywhere?",
        a: "No. The viewer runs in your browser tab and reads the file from your disk. There is no server doing the work, and the page makes no request that carries your file. You can confirm it on the Network tab of your browser's developer tools.",
      },
      {
        q: "How big a file can it open?",
        a: "The viewer never loads the whole file. In our tests a file over 1 GB opened in well under a second, and counting all of its records took a few seconds, reading it in 4 MB windows so memory stays flat.",
      },
      {
        q: "Which Avro compression codecs does it support?",
        a: "Null (uncompressed), deflate and snappy blocks can be previewed. A file compressed with zstandard, bzip2 or xz still gets its schema, header, record count and validation, but its records can't be previewed.",
      },
      {
        q: "Can it read an Avro file from a URL?",
        a: "Yes. Paste the address and the viewer fetches it with HTTP range requests. The server has to allow cross-origin requests (CORS), and for a large remote file the viewer asks before it reads the whole file to count records.",
      },
      {
        q: "Does it open other formats?",
        a: "Yes, Parquet and ORC files open in the same viewer. Drop any of the three and it detects the format from the file itself.",
      },
    ],
  },
  {
    domain: "orcviewer.com",
    format: "ORC",
    ext: ".orc",
    title: "ORC viewer online: open .orc files in your browser",
    h1: "ORC file viewer",
    description:
      "Open an .orc file in your browser and see its schema, stripes and per-column min and max. No install, no account, and your file never leaves your machine.",
    lead:
      "Open an .orc file and see its schema, stripes and the min, max and null count of every column, with no install and no account.",
    sibling: { domain: "avroviewer.com", label: "Avro viewer" },
    cards: [
      {
        h: "The schema, as a tree",
        p: "Structs, lists, maps and unions, with each column's ORC type, laid out so a deeply nested table is readable at a glance.",
      },
      {
        h: "Real column statistics",
        p: "ORC stores min, max and null counts for every column. The viewer reads them straight from the file footer and shows them in a table you can filter, so you can see what's in a column without querying it.",
      },
      {
        h: "Stripes, writer and health",
        p: "Rows and size per stripe, the compression codec, the writer and version, plus checks on the postscript, the footer, the stripes and the statistics, so a corrupt or cut-off file tells you where it breaks.",
      },
    ],
    faq: [
      {
        q: "How do I open an ORC file without installing anything?",
        a: "Drop the .orc file on the viewer above, choose it with the file picker, or paste a URL. The viewer reads the end of the file, where ORC keeps its metadata, and shows the schema and statistics immediately.",
      },
      {
        q: "Is my ORC file uploaded anywhere?",
        a: "No. The viewer runs in your browser tab and reads the file from your disk. There is no server doing the work, and the page makes no request that carries your file. You can confirm it on the Network tab of your browser's developer tools.",
      },
      {
        q: "How big a file can it open?",
        a: "The viewer reads only the tail of the file, where the footer is, and never loads the rest. In our tests a file over 1 GB opened in a fraction of a second.",
      },
      {
        q: "Which ORC compression does it support?",
        a: "Uncompressed, ZLIB, Snappy and LZ4. A file whose footer is compressed with ZSTD or LZO isn't supported yet, and the viewer says so rather than guessing.",
      },
      {
        q: "Can I see the rows?",
        a: "This viewer shows the file's structure and statistics: schema, stripes, and each column's min, max and nulls. It doesn't decode row data.",
      },
      {
        q: "Does it open other formats?",
        a: "Yes, Parquet and Avro files open in the same viewer. Drop any of the three and it detects the format from the file itself.",
      },
    ],
  },
];

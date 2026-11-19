# Preceding optional search runtime

These test-only fixtures come from source commit
`1517ce1ac1d227a47b9f9f00b6669acb75226cba`.
`manifest.json` pins their exact SHA-256 digests.

The four JavaScript files are the actual preceding optional scripts. The gzip
files retain the actual generated homepage, company directory, work page and
homepage search index from that commit. Gzip timestamps are fixed at zero.
They exercise both directions of a mixed-version request: old HTML/index with
new optional code, and new matching metadata with the preceding code.

These snapshots are compatibility inputs, not current company or work facts.
They do not enter the website, publication package, or production asset inventory.

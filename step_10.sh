#!/usr/bin/env bash

UUID=$(uuidgen)
TODAY=$(date -u +"%Y-%m-%d")

# Write OPF metadata (used for archival purposes or manual postprocessing if needed)
cat > metadata.opf <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="bookid">urn:uuid:$UUID</dc:identifier>
    <dc:title>Jay Gould: His Business Career 1867–1892</dc:title>
    <dc:creator id="author">Grodinsky, Julius, 1896–</dc:creator>
    <dc:publisher>University of Pennsylvania Press, Philadelphia</dc:publisher>
    <dc:date>1957</dc:date>
    <dc:language>en</dc:language>
    <dc:description>An examination of the policies of a businessman in the field of speculative or equity capital in the free enterprise era between the Civil War and the Theodore Roosevelt Administration. Digital edition converted from Internet Archive scan.</dc:description>
    <dc:subject>Biography</dc:subject>
    <dc:subject>Business History</dc:subject>
    <dc:subject>Railroad History</dc:subject>
    <dc:subject>American History</dc:subject>
    <dc:rights>© 1957 by The Trustees of the University of Pennsylvania</dc:rights>

    <dc:contributor id="digitizer">Internet Archive</dc:contributor>
    <dc:contributor id="typesetter">Esthie Standard Duong</dc:contributor>

    <dc:source>https://archive.org/details/jaygould0000unse</dc:source>

    <meta property="dcterms:modified">$TODAY</meta>
    <meta name="digitization-sponsor">Kahle/Austin Foundation</meta>
    <meta name="digitization-date">2019</meta>
    <meta name="conversion-note">EPUB converted from Internet Archive digitization by Esthie Standard Duong, ordoliberal.org</meta>
  </metadata>
  <manifest>
    <item id="dummy" href="placeholder.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="dummy"/>
  </spine>
</package>
EOF

# Write Pandoc-compatible YAML metadata (actually used by Pandoc to build final EPUB metadata)
cat > metadata.yaml <<EOF
---
title:
  - type: main
    text: "Jay Gould: His Business Career 1867–1892"
creator:
  - role: author
    text: "Grodinsky, Julius"
contributor:
  - role: digitizer
    text: "Internet Archive"
  - role: typesetter
    text: "Esthie Standard Duong"
publisher: "University of Pennsylvania Press, Philadelphia"
date: "1957"
language: "en"
description: >
  An examination of the policies of a businessman in the field of speculative or equity
  capital in the free enterprise era between the Civil War and the Theodore Roosevelt
  Administration. Digital edition converted from Internet Archive scan.
rights: "© 1957 by The Trustees of the University of Pennsylvania"
subject:
  - Biography
  - Business History
  - Railroad History
  - American History
identifier:
  - scheme: URN
    text: "urn:uuid:$UUID"
...
EOF

# Build EPUB using YAML metadata
pandoc -o jay-gould-biography.epub \
  --metadata-file=metadata.yaml \
  --epub-cover-image=images/cover.png \
  --css=custom.css \
  --toc --toc-depth=2 \
  --split-level=1 \
  --standalone \
  $(ls proper_parts/???_*.md | sort -V)

# Clean up
rm metadata.opf metadata.yaml

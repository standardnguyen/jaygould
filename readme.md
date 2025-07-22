pandoc -o jay-gould-biography.epub \
  --epub-metadata=metadata.xml \
  --metadata title="Jay Gould: His Business Career 1867-1892" \
  --epub-cover-image=images/cover.png \
  --toc --toc-depth=2 \
  --split-level=1 \
  --file-scope \
  --standalone \
  $(ls proper_parts/???_*.md | sort -V)

https://en.wikipedia.org/wiki/File:Mr._Jay_Gould.jpg

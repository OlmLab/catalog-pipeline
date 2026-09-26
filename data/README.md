# data/

Nothing here is committed (see .gitignore). `bootstrap.py` materialises the inputs listed in `config/inputs.json`
into `data/inputs/` (from `~/catalog/data/` or the artifact store) and `make unpack` unzips the current data
package into `data/inputs/data_package/`. Outputs go to `build/`. The published package lives in the
`infant-gut-catalog-data` repo (docs/DATA_LAYOUT.md).

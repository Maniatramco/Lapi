set echo off
whenever sqlerror exit failure rollback
-- Connect as LAPI_OWNER in FREEPDB1 before running. DDL commits in Oracle.
@@lapi_tables/01_user_tbl.sql
@@lapi_tables/02_lapi_items.sql
@@lapi_tables/03_sessions_tbl.sql
@@lapi_tables/04_dataset_tbl.sql
@@lapi_tables/05_model_config_tbl.sql
@@lapi_tables/06_dataset_model_tbl.sql
@@lapi_tables/07_document_tbl.sql
@@lapi_tables/08_prompt_tbl.sql
@@lapi_tables/12_user_dataset_tbl.sql
@@lapi_tables/09_extract_tbl.sql
@@lapi_tables/10_job_tbl.sql
@@lapi_tables/11_review_tbl.sql

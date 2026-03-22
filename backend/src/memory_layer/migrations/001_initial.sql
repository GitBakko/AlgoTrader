-- MANTIS-EVOLUTION: Memory Layer — Initial Schema Migration
-- Migration: 001_initial
-- Description: Creates the initial 3-table schema for LTM + Episodic memory
--
-- Usage (manual):
--   sqlite3 data/memory/mantis_memory.db < migrations/001_initial.sql
--
-- Usage (programmatic — Python):
--   MemoryStore.initialize(db_path)  # auto-applies this via schema.sql

-- Apply the canonical schema definition
.read ../schema.sql

-- Honest Homes Database Schema for Supabase

-- Projects table (from MahaRERA index)
CREATE TABLE IF NOT EXISTS projects (
  id BIGSERIAL PRIMARY KEY,
  rera_id VARCHAR(20) UNIQUE NOT NULL,
  project_name VARCHAR(255) NOT NULL,
  promoter_name VARCHAR(255),
  district VARCHAR(100),
  location VARCHAR(255),
  pincode VARCHAR(10),
  state VARCHAR(100),
  status VARCHAR(50),
  last_modified DATE,
  detail_url TEXT,
  map_url TEXT,
  source_url TEXT,
  fetched_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT status_check CHECK (status IN ('registered', 'deregistered', 'revoked'))
);

-- Create index for fast search
CREATE INDEX IF NOT EXISTS idx_projects_rera_id ON projects(rera_id);
CREATE INDEX IF NOT EXISTS idx_projects_promoter ON projects(promoter_name);
CREATE INDEX IF NOT EXISTS idx_projects_district ON projects(district);
CREATE INDEX IF NOT EXISTS idx_projects_project_name ON projects(project_name);

-- Complaints table (from MahaRERA reputation)
CREATE TABLE IF NOT EXISTS complaints (
  id BIGSERIAL PRIMARY KEY,
  promoter VARCHAR(255) NOT NULL,
  complaint_count INT DEFAULT 0,
  promoter_id VARCHAR(50),
  source_url TEXT,
  fetched_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT unique_promoter UNIQUE(promoter)
);

CREATE INDEX IF NOT EXISTS idx_complaints_promoter ON complaints(promoter);

-- Revoked projects table
CREATE TABLE IF NOT EXISTS revoked_projects (
  id BIGSERIAL PRIMARY KEY,
  rera_id VARCHAR(20) UNIQUE NOT NULL,
  project_name VARCHAR(255),
  promoter VARCHAR(255),
  source_url TEXT,
  fetched_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_revoked_rera_id ON revoked_projects(rera_id);

-- Metadata table
CREATE TABLE IF NOT EXISTS metadata (
  key VARCHAR(100) PRIMARY KEY,
  value TEXT,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO metadata (key, value) VALUES
  ('projects_snapshot_date', '2026-06-02'),
  ('reputation_snapshot_date', '2026-06-04'),
  ('total_projects_rera', '48263'),
  ('total_projects_loaded', '0')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;

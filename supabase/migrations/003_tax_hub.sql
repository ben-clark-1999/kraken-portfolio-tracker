-- Tax Hub Foundation (Phase 5 / Spec 1)
-- Three parallel entry tables + one polymorphic attachment table.

CREATE TABLE tax_deductibles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  description TEXT NOT NULL,
  amount_aud NUMERIC(20, 2) NOT NULL CHECK (amount_aud > 0),
  date_paid DATE NOT NULL,
  type TEXT NOT NULL CHECK (type IN (
    'software', 'hardware', 'professional_development',
    'professional_services', 'crypto_related', 'other'
  )),
  notes TEXT,
  financial_year TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_deductibles_fy ON tax_deductibles(financial_year, date_paid DESC);

CREATE TABLE tax_income (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  description TEXT NOT NULL,
  amount_aud NUMERIC(20, 2) NOT NULL CHECK (amount_aud > 0),
  date_received DATE NOT NULL,
  type TEXT NOT NULL CHECK (type IN (
    'salary_wages', 'freelance', 'interest', 'dividends', 'other'
  )),
  notes TEXT,
  financial_year TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_income_fy ON tax_income(financial_year, date_received DESC);

CREATE TABLE tax_paid (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  description TEXT NOT NULL,
  amount_aud NUMERIC(20, 2) NOT NULL CHECK (amount_aud > 0),
  date_paid DATE NOT NULL,
  type TEXT NOT NULL CHECK (type IN (
    'payg_withholding', 'payg_installment', 'bas_payment', 'other'
  )),
  notes TEXT,
  financial_year TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_paid_fy ON tax_paid(financial_year, date_paid DESC);

CREATE TABLE tax_attachments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_kind TEXT NOT NULL CHECK (parent_kind IN ('deductible', 'income', 'tax_paid')),
  parent_id UUID,                       -- NULL = pending upload not yet bound to an entry
  storage_path TEXT NOT NULL,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_attachments_parent ON tax_attachments(parent_kind, parent_id)
  WHERE parent_id IS NOT NULL;
CREATE INDEX idx_tax_attachments_pending ON tax_attachments(uploaded_at)
  WHERE parent_id IS NULL;

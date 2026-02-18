# CDIL ROI Calculator Template

## Overview

This template provides a **CFO-ready financial model** for calculating the Return on Investment (ROI) of deploying the Clinical Documentation Integrity Layer (CDIL). The calculations are designed to be implemented in Excel or Google Sheets with adjustable assumptions.

## Business Context

**Core Value Proposition:** *"When payers audit with AI, you need AI to defend your revenue."*

CDIL acts as "denial insurance" by:
1. **Preventing denials** through pre-submission documentation improvement
2. **Increasing appeal success rates** via litigation-ready evidence exports
3. **Reducing administrative costs** by avoiding unnecessary appeals

---

## Spreadsheet Layout

### Tab 1: Inputs & Assumptions

#### **Section A: Hospital Baseline Metrics**

| Cell | Parameter | Description | Example Value |
|------|-----------|-------------|---------------|
| B3 | `Annual_NPSR` | Annual Net Patient Service Revenue | $500,000,000 |
| B4 | `Overall_Denial_Rate` | Overall denial rate (0.00 to 1.00) | 0.08 (8%) |
| B5 | `Doc_Denial_Ratio` | % of denials due to documentation issues | 0.40 (40%) |
| B6 | `Current_Appeal_Recovery` | Current appeal recovery rate | 0.25 (25%) |
| B7 | `Cost_Per_Appeal` | Average cost per manual appeal | $150 |
| B8 | `Annual_Claim_Volume` | Total claims submitted annually | 200,000 |

#### **Section B: CDIL Performance Levers**

| Cell | Parameter | Description | Conservative | Moderate | Aggressive |
|------|-----------|-------------|--------------|----------|------------|
| B11 | `Denial_Prevention_Rate` | % of documentation denials prevented pre-submission | 0.05 (5%) | 0.10 (10%) | 0.15 (15%) |
| B12 | `Appeal_Success_Lift` | Incremental appeal success rate improvement | 0.05 (5%) | 0.10 (10%) | 0.15 (15%) |

#### **Section C: CDIL Cost**

| Cell | Parameter | Description | Example Value |
|------|-----------|-------------|---------------|
| B15 | `CDIL_Annual_Cost` | Annual licensing + implementation cost | $250,000 |

---

### Tab 2: Calculations & ROI

#### **Step 1: Calculate Total Documentation-Related Denied Revenue**

| Cell | Formula | Description |
|------|---------|-------------|
| B20 | `=B3 * B4` | Total denied revenue |
| B21 | `=B20 * B5` | Documentation-related denied revenue |

**Example:**
- Total denied revenue: $500M × 0.08 = $40M
- Documentation denied: $40M × 0.40 = $16M

---

#### **Step 2: Calculate Prevented Denials (Pre-Submission Improvement)**

| Cell | Formula | Description |
|------|---------|-------------|
| B24 | `=B21 * B11` | Revenue preserved by preventing denials |
| B25 | `=B21 - B24` | Remaining documentation-related denials |

**Example (Conservative: 5% prevention):**
- Prevented denials: $16M × 0.05 = $800K
- Remaining denials: $16M - $800K = $15.2M

---

#### **Step 3: Calculate Incremental Appeal Recovery**

| Cell | Formula | Description |
|------|---------|-------------|
| B28 | `=B25 * B6` | Current recovered revenue (baseline) |
| B29 | `=B25 * B12` | Incremental recovery gain from appeal lift |

**Example (Conservative: 5% lift):**
- Current recovery: $15.2M × 0.25 = $3.8M
- Incremental gain: $15.2M × 0.05 = $760K

---

#### **Step 4: Calculate Administrative Savings**

| Cell | Formula | Description |
|------|---------|-------------|
| B32 | `=B8 * B4 * B5` | Total documentation-related denials (claim count) |
| B33 | `=B32 * B11` | Appeals avoided due to prevention |
| B34 | `=B33 * B7` | Administrative savings |

**Example (Conservative: 5% prevention):**
- Total doc denials: 200,000 × 0.08 × 0.40 = 6,400 denials
- Appeals avoided: 6,400 × 0.05 = 320 appeals
- Admin savings: 320 × $150 = $48K

---

#### **Step 5: Calculate Total Preserved Revenue & ROI**

| Cell | Formula | Description |
|------|---------|-------------|
| B37 | `=B24 + B29 + B34` | **Total preserved revenue** |
| B38 | `=B15` | CDIL annual cost |
| B39 | `=IF(B38>0, B37/B38, "N/A")` | **ROI Multiple** (X:1) |
| B40 | `=B37 - B38` | **Net Benefit** |

**Example (Conservative Scenario):**
- Total preserved: $800K + $760K + $48K = **$1,608,000**
- CDIL cost: $250K
- ROI Multiple: $1,608K / $250K = **6.4:1**
- Net Benefit: $1,608K - $250K = **$1,358,000**

---

## Scenario Analysis

### Conservative Assumptions (Recommended for CFO Presentation)

- **Denial Prevention Rate:** 5%
- **Appeal Success Lift:** 5%
- **Rationale:** Proven, defensible metrics for first-year deployment

### Moderate Assumptions

- **Denial Prevention Rate:** 10%
- **Appeal Success Lift:** 10%
- **Rationale:** Expected performance after 6-12 months of optimization

### Aggressive Assumptions

- **Denial Prevention Rate:** 15%
- **Appeal Success Lift:** 15%
- **Rationale:** Best-in-class performance with full AI integration

---

## Worked Example: 500-Bed Hospital

### Inputs
- **Annual NPSR:** $500M
- **Denial Rate:** 8%
- **Documentation Denial Ratio:** 40%
- **Current Appeal Recovery:** 25%
- **Cost Per Appeal:** $150
- **Annual Claims:** 200,000
- **CDIL Annual Cost:** $250K

### Conservative Scenario (5% / 5%)

| Metric | Amount |
|--------|--------|
| **Documentation-Related Denied Revenue** | $16,000,000 |
| **Prevented Denials (5%)** | $800,000 |
| **Remaining Denials** | $15,200,000 |
| **Current Appeal Recovery (25%)** | $3,800,000 |
| **Incremental Recovery (5% lift)** | $760,000 |
| **Appeals Avoided (320)** | $48,000 |
| **Total Preserved Revenue** | **$1,608,000** |
| **CDIL Annual Cost** | $250,000 |
| **ROI Multiple** | **6.4:1** |
| **Net Benefit** | **$1,358,000** |

### Moderate Scenario (10% / 10%)

| Metric | Amount |
|--------|--------|
| **Prevented Denials (10%)** | $1,600,000 |
| **Remaining Denials** | $14,400,000 |
| **Incremental Recovery (10% lift)** | $1,440,000 |
| **Appeals Avoided (640)** | $96,000 |
| **Total Preserved Revenue** | **$3,136,000** |
| **ROI Multiple** | **12.5:1** |
| **Net Benefit** | **$2,886,000** |

---

## Usage Instructions for Finance Teams

1. **Copy this template** into Excel or Google Sheets
2. **Enter your hospital's baseline metrics** (Section A)
3. **Select conservative assumptions** for initial analysis (Section B)
4. **Review calculated metrics** to validate reasonableness
5. **Run sensitivity analysis** by adjusting levers (5%, 10%, 15%)
6. **Present to CFO** with conservative scenario as baseline

---

## Key Assumptions & Caveats

### What This Model Assumes
- Documentation denials are accurately tracked in your system
- Current appeal recovery rates are measurable
- CDIL prevents denials through pre-submission quality improvement
- Litigation-ready exports improve appeal success rates

### What This Model Does NOT Include
- Audit risk mitigation (additional upside not modeled)
- Improved documentation quality reducing malpractice exposure
- Staff time savings from automated integrity checks
- Revenue cycle acceleration from faster approvals

### Data Sources Required
- Historical denial data by denial reason code
- Current appeal volumes and success rates
- Average appeal processing costs (staff time + overhead)

---

## Validation Checklist

Before presenting to CFO:

- [ ] Verify denial rate matches published benchmarks (6-10% typical)
- [ ] Confirm documentation denial ratio aligns with HFMA data (30-50%)
- [ ] Validate cost per appeal includes staff time and overhead
- [ ] Ensure CDIL annual cost includes licensing, training, integration
- [ ] Run "reasonableness test": Does ROI exceed 3:1 in conservative scenario?

---

## Support & Customization

This template is designed for general use. For hospital-specific customization:

1. Adjust parameters to match your denial management system
2. Add additional cost categories if needed
3. Include audit risk mitigation (expected value approach)
4. Model multi-year benefits with declining costs

For questions or support, contact your CDIL implementation team.

---

**Template Version:** 1.0  
**Last Updated:** 2026-02-18  
**Recommended Review Frequency:** Quarterly after deployment

# Peer Review Report

> **Instructions:** Complete this form **individually and independently**.
> Do not discuss your ratings with teammates before submitting.
> Submit via EEClass as a **separate, confidential submission** — not in the shared team repo.
> Your teammates will not see this report.
>
> Reference the team's `Team04_WORK_ALLOCATION.md` when completing this form.

---

## Your Details

| Field | Your answer |
|-------|------------|
| Full Name | 洪佳宇 |
| Student ID | 111201029 |
| Team ID | 04 |
| Date submitted | 2026/06/04 |

---

## Rating Scale

| Rating | Meaning |
|--------|---------|
| **5** | Exceeded expectations — delivered more than agreed; helped teammates; consistently high quality |
| **4** | Met expectations fully — delivered exactly what was agreed; on time; good quality |
| **3** | Mostly met expectations — minor shortfalls; one or two items completed late or with help |
| **2** | Partially met expectations — noticeable gaps; teammates had to cover some tasks |
| **1** | Did not meet expectations — significant tasks left incomplete; very limited contribution |

---

## Section A — Self-Assessment

### A1. What did you personally implement?

I was primarily responsible for the write-operation and authentication parts of the relational database implementation. This included `execute_booking`, `execute_cancellation`, `login_user`, `register_user`, `get_user_secret_question`, `verify_secret_answer`, and `update_password` in the PostgreSQL query layer. I also took primary responsibility for PostgreSQL seeding in `skeleton/seed_postgres.py`, including making sure mock data could be loaded consistently and safely.

For the design document, I was the primary author of Section 2, Normalisation Justification, and Section 6, Reflection & Trade-offs. I also contributed to the shared parts of Task 1 and Task 6, including the optional loyalty-points extension, related documentation, and final consistency checks across schema, seed data, query functions, and the design document.

### A2. What challenges did you face?

One challenge was keeping the relational schema, seed script, and query functions consistent after normalization changes. For example, schedule stop data needed to be represented through junction tables instead of relying only on array-style stop order data, so related queries and seed logic had to be checked together.

Another challenge was ensuring that user authentication met the grading policy. We needed to avoid plain-text password storage and avoid simple SHA-style hashing, so I verified that registration, password updates, login verification, and seeded users all used bcrypt consistently. I resolved these issues by testing the seed flow, reviewing the relevant functions, and checking that the database stored hashes instead of plain text.

### A3. Self-rating

| Criterion | Rating (1–5) | Justification (1–2 sentences) |
|-----------|-------------|-------------------------------|
| I delivered the tasks assigned to me in the work allocation | 5 | I completed my assigned relational write operations, authentication functions, seeding work, and design-document sections. I also helped with shared final checks and Task 6 integration. |
| The quality of my work was satisfactory | 5 | I focused on correctness, database constraints, transaction behavior, password security, and consistency between the code and documentation. |
| I communicated well and kept the team informed | 5 | I kept the team updated when schema or query changes affected other parts of the project, especially where seed data and documentation needed to match implementation. |
| I met deadlines agreed within the team | 5 | I completed my assigned parts on time and helped with final integration before submission. |
| **Overall self-rating** | **5** | I believe I contributed fully and consistently, while also supporting the team in shared tasks and final verification. |

### A4. Estimated contribution percentage

> My estimated contribution: **33.4%**

---

## Section B — Peer Assessments

### B1. Assessment of Teammate 1

| Field | Your answer |
|-------|------------|
| Teammate's full name | 吳怡臻 |
| Teammate's student ID | 112707 |

#### What did this teammate deliver?

吳怡臻 was primarily responsible for the Neo4j graph database parts of the project, including graph design and seeding in `seed_neo4j.py` and `seed.cypher`, as well as Neo4j query functions in `databases/graph/queries.py`. She also served as the primary author for Design Document Section 3, Graph Database Design Rationale, and Section 5, AI Tool Usage Evidence. In addition, she supported other shared tasks such as Task 1, Task 6, and final documentation review.

#### Did their actual contribution match the agreed work allocation?

Yes. Her actual contribution matched the work allocation. She completed the graph-related responsibilities and also helped review and improve shared parts of the project.

#### Peer rating for this teammate

| Criterion | Rating (1–5) | Justification (1–2 sentences) |
|-----------|-------------|-------------------------------|
| Delivered the tasks assigned in the work allocation | 5 | She completed the Neo4j seed, graph query, and graph-documentation responsibilities assigned to her. |
| Quality of their work was satisfactory | 5 | Her graph work correctly modeled stations, relationships, and routing behavior, and she helped make the implementation match the grading requirements. |
| Communicated well and kept the team informed | 5 | She communicated clearly when working on graph-related issues and coordinated well with the rest of the team. |
| Met deadlines agreed within the team | 5 | Her assigned work was completed in time for integration and final checking. |
| **Overall rating for this teammate** | **5** | She contributed strongly and reliably, and her work was an important part of the final project. |

#### Estimated contribution percentage for this teammate

> My estimate of their contribution: **33.3%**

---

### B2. Assessment of Teammate 2

| Field | Your answer |
|-------|------------|
| Teammate's full name | 吳欣庭 |
| Teammate's student ID | 111401549 |

#### What did this teammate deliver?

吳欣庭 was primarily responsible for many of the core PostgreSQL query functions, including availability, fare, seat, user profile, user booking, and payment information queries. She was also the primary author for Design Document Section 1, ER Diagram, and Section 4, Vector / RAG Design. She supported relational schema design, write operations, authentication, graph work, Task 6, and final integration checks.

#### Did their actual contribution match the agreed work allocation?

Yes. Her actual contribution matched the work allocation. She completed the major query and documentation tasks assigned to her, and she also supported the team in cross-checking implementation details.

#### Peer rating for this teammate

| Criterion | Rating (1–5) | Justification (1–2 sentences) |
|-----------|-------------|-------------------------------|
| Delivered the tasks assigned in the work allocation | 5 | She completed her assigned PostgreSQL query functions and design-document sections. |
| Quality of their work was satisfactory | 5 | Her work was detailed and useful for the main user-facing database workflows, including schedule, fare, seat, and account-related queries. |
| Communicated well and kept the team informed | 5 | She coordinated well with the team and helped make sure query behavior and documentation stayed aligned. |
| Met deadlines agreed within the team | 5 | Her assigned work was completed on time and ready for final integration. |
| **Overall rating for this teammate** | **5** | She contributed consistently and effectively, and her work helped keep the overall project balanced. |

#### Estimated contribution percentage for this teammate

> My estimate of their contribution: **33.3%**

---

## Section C — Contribution Percentage Summary

All members, including myself, sum to 100%.

| Member | Your estimated % | Notes |
|--------|----------------|-------|
| 洪佳宇 | 33.4% | I completed my assigned relational write, authentication, seeding, and documentation tasks, and helped with shared Task 6 integration. |
| 吳怡臻 | 33.3% | She led the graph database and graph-query work and contributed to shared documentation and final review. |
| 吳欣庭 | 33.3% | She led many core PostgreSQL query functions, the ER diagram, and the Vector/RAG documentation. |
| **Total** | **100%** | The workload was very evenly distributed across the three members. |

---

## Section D — Overall Team Reflection

### D1. What went well in the team's collaboration?

The collaboration went well because the three members divided the project into clear areas: relational write/authentication/seeding, PostgreSQL query functions, and Neo4j graph implementation. Even though each person had a primary area, everyone also supported shared tasks such as schema review, Task 6, documentation, and final testing. Overall, the workload felt balanced and communication was smooth.

### D2. What would you do differently if you did this project again?

If we did this project again, I would set up a clearer testing checklist earlier in the project. Some issues only became obvious when schema, seed data, and query functions were tested together, so earlier end-to-end checks would make integration easier. I would also keep the design document updated continuously instead of doing a larger final documentation pass near the end.

### D3. Is there anything else the markers should know about team dynamics or individual contributions?

Nothing negative to add. I think all three members contributed fairly and responsibly. The work was divided evenly, everyone completed their assigned parts, and we supported each other when implementation details overlapped.

---

## Declaration

I confirm that this peer review reflects my honest and independent assessment.
I understand it will be kept confidential from my teammates.

**Signed:** 洪佳宇 **Date:** 2026/06/04


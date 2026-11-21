# B research: beyond a convenient Python/.NET adapter

The purpose of B is not to invent shorter spelling for existing programs. Its hypothesis is that a **checked semantic representation plus reusable capabilities** can reduce the decisions an AI needs to generate, increasing verified behavior per total unit of compute.

## Research process

The approach draws on the creativity/innovation framework Tobias Degsell describes in his lectures: work across disciplines; retain a clear *why*; combine knowledge and diverse perspectives; value productive friction; implement and measure rather than stopping with an interesting idea. Sources: [Folkhälsomyndigheten conference documentation](https://www.folkhalsomyndigheten.se/contentassets/1f8d3847512c4d76b93bd86b60b9d38a/dokumentation-dialogforum.pdf), [Effekten conversation about creativity, innovation and digitalisation](https://www.effekten.se/kreativitet-innovation-digitalisering/).

In engineering terms every proposal gets a direct competitor, a measurable hypothesis and a **kill criterion**. A clever language feature without a demonstrated benefit should not become part of B merely because it sounds attractive.

## Candidate experiments

### A. Evidence-carrying operations (priority: HIGH)

Combine *mathematical contracts*, *programming language type systems* and *reusable libraries*. Let a B operation be defined by an input/output contract, explicit effects and optional proof obligations. Reuse checked properties instead of generating an algorithm and its proof repeatedly. **Strictly distinguish** proved, violated, unknown and trusted-external. Never allow an implementation to weaken its own acceptance requirements.

**Test:** 50 independently specified transformation tasks; compare checked native B operations against ordinary Python + tests under matched compute budgets. **Kill:** no decrease in regressions or total time/cost, or too many false refusals to be useful.

### B. Effect/capability types (priority: HIGH)

Combine ideas from *Rust ownership*, *effect systems*, *least-privilege security* and *biological compartmentalization*. A B function can declare or infer whether it reads, writes, communicates, allocates unboundedly or modifies shared state. The checker rejects forbidden combinations before execution. Foreign-library effects start as **unknown**, not pure, unless they have a defensible declared contract.

**Test:** detect attempts to access network/files, duplicate side-effecting calls and unintended mutation in carefully constructed projects. **Kill:** bypassable effects through common foreign calls or unacceptable broad denials.

### C. Native semantic assets (priority: MEDIUM)

Combine *dimensional analysis*, *dependent types* and *tensor shape inference*. Money, time, physical units and array shapes become types or contract parameters. Matrix dimensions and incompatible units are checked before code runs. Reuse specialized libraries to execute the actual numerical workload.

**Test:** mixed-currency, date/time and matrix-shape tasks where incorrect conventional programs still typecheck. **Kill:** model-generated annotations are so often wrong/omitted that total correct task completion drops.

### D. Incremental semantic compilation (priority: MEDIUM)

Combine *incremental build graphs*, *transactional databases* and *functional dependency analysis*. Give BIR nodes stable identities; a modification invalidates only the dependent subgraph and its associated obligations. This is a language/compiler capability, not an agent-management feature.

**Test:** repeated changes to a medium codebase; measure unnecessary recomputation and previously working behavior lost. **Kill:** no improvement beyond normal incremental compilers and test tools.

### E. Portable capability adapters (priority: MEDIUM)

Combine *WebAssembly Component Model/WIT*, *C ABIs*, *JVM metadata* and *protocol schemas* through BIR. Add new runtime backends only for cases where library reuse or performance is quantifiably improved. Moving data must respect representation, ownership, lifetime, copies and effects.

**Test:** a real library in a third ecosystem, end-to-end; compare correctness/performance and integration cost with current FFI. **Kill:** adapters reproduce existing FFI with little benefit.

### F. Model-native BIR generation (priority: RESEARCH)

Instead of prompting the model for hand-formatted source, generate typed operations/arguments through a constrained builder that can refuse impossible next steps. Keep text B as one view of the same meaning. Evaluate efficiency with actual tokenizer costs, context, repair attempts and model training. **Do not assume** fewer characters mean fewer generated tokens.

**Test:** same model, same benchmark tasks and library access, same total budget; compare source B, BIR builder and Python. **Kill:** model-native format fails to beat conventional tools on end-to-end cost per correct result.

## Preferred order

1. Improve Python metadata coverage enough that a real large library has usable, typed operations. This is currently the biggest practical bottleneck.
2. Pilot effect/capability contracts on a *small, restricted set* of B operations.
3. Pilot proofs/invariants on bounded data transformations; keep proof outcomes explicit.
4. Add a third real runtime only when an interoperability test demonstrates value.
5. Test model-generated programs with independent correctness oracles, including repeated changes, *before* promoting any claim that B is a better language for AI.

The most important experimental result may be a **negative one**: if existing Rust/Python/TypeScript tooling plus constrained generation achieves the same correctness and cost, a new language is not justified. In that case BIR or the verification methods can still be useful as independent tools.

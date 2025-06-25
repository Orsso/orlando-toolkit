```mermaid
gantt
    title Orlando Toolkit – Refactor Roadmap
    dateFormat  YYYY-MM-DD
    %% NOTE: Adjust dates if the start shifts; durations are indicative.

    section Phase 1 – Project Skeleton
    Setup package skeleton               :done,   p1, 2025-07-01, 7d

    section Phase 2 – Core Models & Helpers
    Extract DitaContext model            :done,   p2a, after p1, 2d
    Extract reusable helpers             :done,   p2b, after p2a, 2d
    Move parser utilities                :done,   p2c, after p2b, 3d
    Clean converter imports              :done,   p2d, after p2c, 2d

    section Phase 3 – Split Converter
    Create generators package            :done,   p3a, after p2, 3d
    Extract table builder                :done,   p3b, after p3a, 3d
    Extract colour utilities             :done,   p3c, after p3b, 3d
    Introduce ConversionService facade   :done,   p3d, after p3c, 5d

    section Phase 4 – Configuration Layer
    Introduce ConfigManager & YAML       :active, p4, after p3, 7d
    Migrate converter implementation     :active, p4a, after p4, 5d
    %% p4a note: wrappers added in legacy file, convert_docx_to_dita migration ongoing
    Copy convert_docx_to_dita to core   :done, p4a1, after p4a, 2d
    %% p4a1 completed: function copied and wrapper added
    Replace helper imports              :p4a2, after p4a1, 1d
    :done, p4a2, after p4a1, 1d
    Add legacy wrapper                  :p4a3, after p4a2, 1d
    :done, p4a3, after p4a2, 1d
    Remove dead code from src           :p4a4, after p4a3, 1d
    :done, p4a4, after p4a3, 1d

    section Phase 5 – GUI Refactor
    Rewire GUI to use ConversionService  :done, p5a, after p4, 2d
    Remove src.* imports from UI         :done, p5b, after p5a, 2d

    section Phase 6 – Testing & QA
    Unit + regression test suite         :p6, after p5, 7d

    section Phase 7 – Documentation
    Update README & developer docs       :active, p7, after p6, 7d

    %% Phase 7 subtasks
    Architecture overview doc           :done,   p7a, after p7, 1d
    Module-level README stubs           :done,   p7b, after p7a, 2d
    Mermaid diagrams (runtime, dataflow):done,   p7c, after p7a, 1d
    Update top-level README             :active, p7d, after p7b, 1d
    API reference skeleton (Sphinx)     :p7e, after p7d, 2d

    section Phase 8 – Legacy Cleanup
    Remove src/docx_to_dita_converter   :done,   p8d, after p8c, 1d
    Remove unused helpers in src/       :p8b, after p8, 1d
    Validate 0 legacy imports           :p8c, after p8b, 1d
    Tag refactor completion             :p8h, after p8g, 0d

    # Detailed work plan
    Move src/ui to package              :done,   p8a, after p7, 1d
    Move DTDs into resources            :done,   p8b, after p8a, 1d
    Migrate style_analyzer              :done,   p8c, after p8b, 1d
    Purge remaining src folder          :done,   p8e, after p8d, 1d
    Update run.py imports               :done,   p8f, after p8e, 1d
    Final grep for src. imports         :active, p8g, after p8f, 0d
    Tag refactor completion             :p8h, after p8g, 0d
```
# Orlando Toolkit - Development Timeline

```mermaid
gantt
    title Orlando Toolkit Development Phases
    dateFormat X
    axisFormat %s

    section Phase 1 - Project Skeleton
    Setup package skeleton               :done, p1, 0, 1

    section Phase 2 - Core Models & Helpers
    Extract DitaContext model            :done, p2a, 1, 2
    Extract reusable helpers             :done, p2b, 2, 3
    Move parser utilities                :done, p2c, 3, 4
    Clean converter imports              :done, p2d, 4, 5

    section Phase 3 - Split Converter
    Create generators package            :done, p3a, 5, 6
    Extract table builder                :done, p3b, 6, 7
    Extract colour utilities             :done, p3c, 7, 8
    Introduce ConversionService facade   :done, p3d, 8, 9

    section Phase 4 - Configuration Layer
    Introduce ConfigManager & YAML       :done, p4, 9, 10
    Migrate converter implementation     :done, p4a, 10, 11
    Copy convert_docx_to_dita to core   :done, p4a1, 11, 12
    Replace helper imports              :done, p4a2, 12, 13
    Add legacy wrapper                  :done, p4a3, 13, 14
    Remove dead code from src           :done, p4a4, 14, 15

    section Phase 5 - GUI Refactor
    Rewire GUI to use ConversionService  :done, p5a, 15, 16
    Remove src imports from UI           :done, p5b, 16, 17

    section Phase 6 - Testing & QA
    Unit test suite development          :p6, 17, 18

    section Phase 7 - Documentation
    Architecture overview doc           :done, p7a, 18, 19
    Module-level README stubs           :done, p7b, 19, 20
    Mermaid diagrams                    :done, p7c, 20, 21
    Update top-level README             :done, p7d, 21, 22

    section Phase 8 - Legacy Cleanup
    Move UI to package                  :done, p8a, 22, 23
    Move DTDs into resources            :done, p8b, 23, 24
    Migrate style_analyzer              :done, p8c, 24, 25
    Remove src converter                :done, p8d, 25, 26
    Purge remaining src folder          :done, p8e, 26, 27
    Update run.py imports               :done, p8f, 27, 28
    Final cleanup and validation        :done, p8g, 28, 29
```
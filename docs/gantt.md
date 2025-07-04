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

    section Phase 9 - Instant Depth Filtering
    Parse all heading levels (remove depth gate)         :done, p9a, 29, 30
    Annotate topics with data-level attribute            :done, p9b, after p9a, 1
    Remove re-parse thread in GUI                        :done, p9c, after p9b, 1
    Update Structure tab to client-side filter only      :done, p9d, after p9c, 1
    Implement packaging pruner by topic_depth            :done, p9e, after p9d, 1
    Regression & UX testing                              :done, p9f, after p9e, 1

    %% ------------------------------------------------------------------
    %% PHASE 10 – Word-consistent Heading Detection
    %% ------------------------------------------------------------------
    section Phase 10 - Heading Detection Parity
    Design outline-level inheritance algorithm         :done, p10a, after p9f, 1
    Implement _inherit_outline_level helper            :done, p10b, after p10a, 1
    Integrate helper in build_style_heading_map        :done, p10c, after p10b, 1
    Extend generic Heading/Titre regex                 :done, p10d, after p10c, 1
    Add unit tests for inheritance & regex             :done, p10e, after p10d, 1
    Regression test with sample DOCX set               :done, p10f, after p10e, 1
    Update docs & README                               :done, p10g, after p10f, 1
    Final code review & merge                          :done, p10h, after p10g, 1

    %% ------------------------------------------------------------------
    %% PHASE 11 – Depth-Merge of Sub-topics
    %% ------------------------------------------------------------------
    section Phase 11 - Depth Merge Behaviour
    Specs & architecture notes                       :done, p11a, after p10h, 1
    Implement merge_topics_below_depth() helper      :done, p11b, after p11a, 2
    Integrate helper in ConversionService.prepare    :done, p11c_core, after p11b, 1
    Hook merge into StructureTab depth change        :done, p11d_gui, after p11c_core, 1
    Add toggle switch (real-time merge on/off)       :done, p11e_gui_toggle, after p11d_gui, 1
    Busy-indicator / disable UI during merge         :done, p11f_gui, after p11e_gui_toggle, 1
    Fix cross-refs / ID deduplication                :done, p11g, after p11f_gui, 1
    Replace live context on depth change           :done, p11g2, after p11g, 1
    Unit tests (core + GUI functional)               :p11h, after p11g, 1
    Update docs & user guide                         :p11i, after p11h, 1
    Regression & performance testing                 :p11j, after p11i, 1
    Final review & release                           :p11k, after p11j, 1

    %% ------------------------------------------------------------------
    %% PHASE 12 – Dynamic Section/Module Logic
    %% ------------------------------------------------------------------
    section Phase 12 - Dynamic Section/Module Decision
    Architecture design & data structures           :done, p12a, after p11k, 2
    Create HeadingNode model & hierarchy builder    :done, p12b, after p12a, 3
    Implement structure analysis (Pass 1)           :done, p12c, after p12b, 2
    Role determination algorithm                     :done, p12d, after p12c, 1
    DITA generation from structure (Pass 2)         :done, p12e, after p12d, 3
    Content block preservation & migration          :done, p12f, after p12e, 2
    Integration with existing helpers                :done, p12g, after p12f, 1
    Replace main conversion loop                     :done, p12h, after p12g, 2
    Comprehensive testing & validation               :done, p12i, after p12h, 3
    Performance benchmarking & optimization         :done, p12j, after p12i, 1
    Documentation & code review                     :done, p12k, after p12j, 1
    Final integration & regression testing          :done, p12l, after p12k, 2

---

## Phase 12 Implementation Summary (COMPLETED)

**Objective:** Transform conversion from immediate topic creation to a two-pass approach that defers section vs module decisions until complete document structure is analyzed.

### ✅ **Completed Deliverables:**

#### **P12A-C: Architecture & Core Implementation**
- **`HeadingNode`** dataclass in `core/models.py` for hierarchical document representation
- **`structure_builder.py`** module with complete two-pass conversion logic:
  - `build_document_structure()` - analyzes document and builds hierarchy
  - `determine_node_roles()` - applies section vs module decision logic
  - `generate_dita_from_structure()` - creates proper DITA topics
  - `_add_content_to_topic()` - preserves all content formatting

#### **P12D-E: Decision Logic & DITA Generation**
- **Smart Role Determination**: `has_children()` → Section, `no_children()` → Module
- **Orlando Compatibility**: Sections remain empty, modules contain content
- **Recursive Processing**: Handles complex nested hierarchies correctly

#### **P12F-H: Integration & Migration**
- **Updated `convert_docx_to_dita()`** to use new two-pass approach
- **Preserved All Functionality**: images, formatting, style mapping, metadata, table percentage widths
- **Clean Import Structure**: proper module organization and exports

#### **P12I-L: Testing & Cleanup**
- **Dead Code Removal**: cleaned up old lazy-creation logic and unused imports
- **Functionality Validation**: end-to-end testing with real documents
- **Performance Verified**: two-pass approach maintains conversion speed

### 🎯 **Success Criteria Met:**

| Requirement | Status | Result |
|-------------|--------|---------|
| Single heading + content → Module (not Section + empty Module) | ✅ **ACHIEVED** | Document: "TABLEAU" + table → Module "TABLEAU" with content |
| Heading + content + sub-headings → Section + Module + Sub-modules | ✅ **ACHIEVED** | Proper hierarchy with Orlando-compliant structure |
| Zero regression in existing functionality | ✅ **ACHIEVED** | All existing features preserved |
| Performance within acceptable limits | ✅ **ACHIEVED** | Two-pass approach efficient |
| Orlando CMS compatibility | ✅ **ACHIEVED** | Generated DITA follows Orlando requirements |

### 📁 **Files Modified:**
- `core/models.py` - Added HeadingNode dataclass
- `core/converter/structure_builder.py` - New two-pass conversion module
- `core/converter/docx_to_dita.py` - Updated to use structure builder
- `core/converter/__init__.py` - Updated exports

### 🔄 **Architecture Impact:**
The implementation maintains the project's pure-function, no-side-effects design while introducing a cleaner separation between document analysis and DITA generation phases.
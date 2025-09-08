# Runtime Flow

```mermaid
sequenceDiagram
    participant User
    participant GUI
    participant Ctrl as "Controller"
    participant Svc as "Service"
    participant Conv as "Converter"
    participant Prev as "Preview"
    participant FS as "File System"

    alt Plugin-owned workflow (WorkflowLauncher)
        User->>GUI: Launch plugin workflow
        GUI->>Plugin: register_workflow_launcher(...).launch()
        Plugin-->>Svc: convert(path, metadata)
    else Default workflow
        User->>GUI: Select Document
        GUI->>Svc: convert(path, metadata)
    end

    Svc->>Conv: Plugin Handler convert_to_dita()
    Conv-->>Svc: DitaContext
    Svc-->>GUI: context ready
    GUI-->>User: Home summary + inline metadata
    User->>GUI: Continue to workspace
    Note over GUI,Ctrl: Structure tab uses StructureController
    Note over Ctrl,Svc: Depth/style merge via StructureEditingService + UndoService

    User->>GUI: Edit structure / change depth
    GUI->>Ctrl: handle_depth_change / edits
    Ctrl->>Svc: apply_depth_limit(...)
    Svc-->>Ctrl: updated context
    Ctrl-->>GUI: refresh tree + preview

    GUI->>Ctrl: render_html_preview / compile_preview
    Ctrl->>Prev: render_html_preview / compile_topic_preview
    Prev-->>Ctrl: HTML/XML content
    Ctrl-->>GUI: display preview

    User->>GUI: Generate Package
    GUI->>Svc: prepare_package(ctx)
    GUI->>Svc: write_package(ctx, path)
    Svc->>Conv: save_dita_package(tmp_dir)
    Svc->>FS: make_archive(.zip)
    Svc-->>GUI: .zip ready
    GUI-->>User: Save dialog
```

Notes:
- When a plugin registers a WorkflowLauncher, it owns file selection and progress. On success it must call app_ui.on_conversion_success(context). Otherwise, the default flow applies.


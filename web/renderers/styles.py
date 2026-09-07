def render_global_filter_styles() -> str:

    return """
    <style>

    #global-filter {
        margin-bottom: 34px;
    }

    .global-filter-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 20px;
    }

    .global-filter-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 20px;
        margin-bottom: 18px;
    }

    .global-filter-header h2 {
        margin: 0 0 6px;
    }

    .global-filter-grid {
        display: grid;
        grid-template-columns:
            repeat(
                3,
                minmax(180px, 1fr)
            );
        gap: 14px;
    }

    .global-filter-grid label {
        display: flex;
        flex-direction: column;
        gap: 7px;
    }

    .global-filter-grid label span {
        color: var(--muted);
        font-size: .85rem;
        font-weight: 600;
    }

    .global-filter-grid select {
        width: 100%;
        padding: 11px 12px;
        border-radius: 9px;
        border: 1px solid var(--border);
        background: var(--surface2);
        color: var(--text);
        font-size: 1rem;
    }

    #global-filter-reset {
        border: 1px solid var(--border);
        background: var(--surface2);
        color: var(--text);
        border-radius: 9px;
        padding: 10px 14px;
        cursor: pointer;
        white-space: nowrap;
    }

    #global-filter-reset:hover {
        background: var(--border);
    }

    .global-filter-status {
        margin-top: 14px;
        color: var(--muted);
        font-size: .9rem;
        min-height: 20px;
    }

    .ml-filter-status {
        color: var(--muted);
        font-size: .9rem;
        margin-bottom: 14px;
    }

    [hidden] {
        display: none !important;
    }

    @media (max-width: 700px) {

        .global-filter-header {
            display: block;
        }

        #global-filter-reset {
            margin-top: 12px;
        }

        .global-filter-grid {
            grid-template-columns: 1fr;
        }

    }

    </style>
    """

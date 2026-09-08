// ============================================================
// src/components/admin/DocsPane.jsx — PDF upload + document list.
//
// CONCEPT (file upload): build a FormData, POST it (multipart). Never
// JSON — a file can't go in JSON. The api.upload() helper sends the
// FormData and lets fetch set the multipart boundary. Validation here:
// accept only .pdf + non-empty (the backend re-checks — first line of
// defense is UX, last is the API).
// ============================================================

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api.js";
import { Card, ErrorBanner, EmptyState, Pagination, Spinner } from "../shared/ui.jsx";

const PER_PAGE = 6;

export default function DocsPane() {
  const [rows, setRows] = useState(null);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const qs = new URLSearchParams({ page, per_page: PER_PAGE });
      const data = await api.get(`/api/documents?${qs.toString()}`);
      setRows(data.items);
      setPages(data.pages);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    }
  }, [page]);

  useEffect(() => { load(); }, [load]);

  // Client-side file validation BEFORE upload.
  const pickFile = (e) => {
    const f = e.target.files?.[0];
    setFileError(null);
    setUploadResult(null);
    if (!f) return setFile(null);
    if (!f.name.toLowerCase().endsWith(".pdf"))
      return setFileError("Only PDF files are supported.");
    if (f.size === 0) return setFileError("Empty files are not supported.");
    setFile(f);
  };

  const upload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.upload("/ingest", fd);
      setUploadResult(`Ingested ${res.ingested} chunks (doc ${res.doc_id.slice(0, 8)}…).`);
      setFile(null);
      load(); // refresh the list to include the new doc
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const remove = async (id, name) => {
    if (!window.confirm(`Delete metadata for "${name}"?`)) return;
    try {
      await api.delete(`/api/documents/${id}`);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <Card title="Documents & uploads">
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {/* Upload box */}
      <div className="mb-6 border border-dashed border-hairline p-5 flex flex-col sm:flex-row items-center gap-3 justify-between flex-wrap">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">Upload a clinical manual (PDF)</p>
          <p className="text-xs text-muted">
            Text is PII-redacted before embedding. Label follows your role.
          </p>
          {fileError && <p className="text-xs text-signal mt-1">{fileError}</p>}
          {uploadResult && <p className="text-xs text-green-700 mt-1">{uploadResult}</p>}
        </div>
        <div className="flex items-center gap-2 min-w-0">
          <input
            type="file"
            accept="application/pdf"
            onChange={pickFile}
            className="text-sm text-muted file:mr-3 file:border file:border-hairline
              file:bg-white file:px-3 file:py-1.5 file:text-iodine-700
              file:text-sm file:font-medium file:hover:border-iodine-600"
          />
          <button
            onClick={upload}
            disabled={!file || uploading}
            className="btn-primary max-w-[220px]"
            title={file ? file.name : ""}
          >
            <span className="inline-block max-w-full truncate">
              {uploading ? "Ingesting…" : file ? `Upload ${file.name}` : "Upload"}
            </span>
          </button>
        </div>
      </div>

      {/* List with pagination + delete */}
      {!rows ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <EmptyState text="No documents uploaded yet." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="thead">
                <th>Filename</th>
                <th>Chunks</th>
                <th>Access label</th>
                <th>Size</th>
                <th>Uploaded</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody className="tbody">
              {rows.map((d) => (
                <tr key={d.id} className="border-b border-hairline">
                  <td className="py-2 pr-3 font-medium wrap-anywhere">{d.filename}</td>
                  <td className="py-2 pr-3">{d.chunk_count}</td>
                  <td className="py-2 pr-3">
                    <span className="text-xs border border-hairline bg-white px-2 py-0.5">
                      {d.rbac_label}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-muted">
                    {d.file_size_bytes != null
                      ? `${(d.file_size_bytes / 1024).toFixed(0)} KB`
                      : "—"}
                  </td>
                  <td className="py-2 pr-3 text-muted whitespace-nowrap">
                    {new Date(d.created_at).toLocaleString()}
                  </td>
                  <td className="py-2">
                    <button className="btn-ghost" onClick={() => remove(d.id, d.filename)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pagination page={page} pages={pages} total={total} onChange={setPage} />
    </Card>
  );
}
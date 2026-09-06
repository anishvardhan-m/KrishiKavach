// Expert help card — explains how the farmer can reach an agronomist.

interface Props {
  onDone: () => void
  onSpeak: () => void
}

export function ExpertCard({ onDone, onSpeak }: Props) {
  return (
    <div className="card" role="region" aria-label="Expert help">
      <h2>Expert help</h2>
      <p>
        An agriculture expert can look at your photo and tell you what to do.
        This is free for farmers.
      </p>
      <div
        style={{
          background: "#f0fdf4",
          border: "1px solid #bbf7d0",
          borderRadius: 12,
          padding: 16,
          marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, color: "#14532d" }}>
          📞 Krishi Vigyan Kendra helpline
        </div>
        <div style={{ fontSize: 22, fontWeight: 700, marginTop: 6 }}>
          1800-103-AGRI
        </div>
        <div style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>
          Toll-free, every day from 6 AM to 10 PM
        </div>
      </div>
      <div
        style={{
          background: "#fff7ed",
          border: "1px solid #fed7aa",
          borderRadius: 12,
          padding: 16,
          marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, color: "#9a3412" }}>
          📸 For your photo
        </div>
        <p style={{ margin: "6px 0 0", fontSize: 15 }}>
          When you call, please share the same photo you just took. The
          expert will see the same image and can give better advice.
        </p>
      </div>
      <div className="inline-actions">
        <button className="small-btn primary" onClick={onSpeak} type="button">
          🔊 Listen
        </button>
        <button className="small-btn" onClick={onDone} type="button">
          ← Back
        </button>
      </div>
    </div>
  )
}

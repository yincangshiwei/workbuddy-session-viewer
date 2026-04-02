export default function ProcessingModal({ visible, text = "处理中..." }) {
  if (!visible) return null;

  return (
    <div className="modal-overlay active processing-overlay">
      <div className="processing-modal" role="status" aria-live="polite" aria-busy="true">
        <div className="processing-spinner" />
        <div className="processing-text">{text}</div>
      </div>
    </div>
  );
}

export default function Pagination({ currentPage, totalPages, setCurrentPage, filteredCount, totalCount }) {
  return (
    <div className="pagination">
      <span className="countDisplay">显示 {filteredCount} / {totalCount} 条</span>
      <button onClick={() => setCurrentPage(1)} disabled={currentPage <= 1}>首页</button>
      <button onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={currentPage <= 1}>上一页</button>
      <span>第 {currentPage} / {totalPages} 页</span>
      <button onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage >= totalPages}>下一页</button>
      <button onClick={() => setCurrentPage(totalPages)} disabled={currentPage >= totalPages}>末页</button>
    </div>
  );
}

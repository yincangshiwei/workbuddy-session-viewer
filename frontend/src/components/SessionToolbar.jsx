export default function SessionToolbar({
  search,
  setSearch,
  statusFilter,
  setStatusFilter,
  cwdFilter,
  setCwdFilter,
  dateFrom,
  setDateFrom,

  dateTo,
  setDateTo,
  clearFilters,
  refresh,
  loading,
  exportSelected,
  shareSelected,
  selectedCount,
  openDeleteSelected,

  filteredCount,
  totalCount,
  autoRefreshing,
  countdown,
}) {
  return (
    <div className="toolbar">
      <input type="text" value={search} onChange={(e) => { setSearch(e.target.value); }} placeholder="🔍 搜索标题 / ID / 目录..." />
      <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); }}>
        <option value="">全部状态</option>
        <option value="completed">Completed</option>
        <option value="working">Working</option>
        <option value="failed">Failed</option>
        <option value="cancelled">Cancelled</option>
        <option value="inprogress">InProgress</option>
      </select>
      <select value={cwdFilter} onChange={(e) => { setCwdFilter(e.target.value); }}>
        <option value="">全部目录</option>
        <option value="missing">❌ 目录缺失</option>
        <option value="exists">✅ 目录存在</option>
      </select>

      <div className="date-group">

        <span>从</span>
        <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); }} />
        <span>到</span>
        <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); }} />
      </div>
      <button onClick={clearFilters}>清除筛选</button>
      <button onClick={refresh} disabled={loading}>{loading ? "处理中..." : "刷新"}</button>
      <button onClick={exportSelected} disabled={loading || selectedCount === 0}>导出对话({selectedCount})</button>
      <button onClick={shareSelected} disabled={loading || selectedCount === 0}>分享对话({selectedCount})</button>
      <button className="btn-danger" onClick={openDeleteSelected} disabled={loading || selectedCount === 0}>批量删除({selectedCount})</button>

      <span className="countDisplay">显示 {filteredCount} / {totalCount} 条</span>
      <span className={`auto-refresh-tip ${autoRefreshing ? "active" : ""}`}>{autoRefreshing ? "自动刷新中..." : `自动刷新倒计时：${countdown}s`}</span>
    </div>
  );
}

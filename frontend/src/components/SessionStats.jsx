export default function SessionStats({ stats }) {
  return (
    <div className="stats">
      <div className="stat"><div className="num">{stats.total}</div><div className="lbl">总任务</div></div>
      <div className="stat"><div className="num c-ok">{stats.completed}</div><div className="lbl">已完成</div></div>
      <div className="stat"><div className="num c-run">{stats.working}</div><div className="lbl">进行中</div></div>
      <div className="stat"><div className="num c-err">{stats.missing}</div><div className="lbl">目录缺失</div></div>
      <div className="stat"><div className="num c-info">{stats.withFc}</div><div className="lbl">有文件变更</div></div>
    </div>
  );
}

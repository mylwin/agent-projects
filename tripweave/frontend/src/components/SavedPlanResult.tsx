import { CalendarDays, MapPin, UsersRound } from "lucide-react";
import type {
  ResearchReport,
  SavedPlanResult as PlanResult,
} from "../api/projects";

const topicNames: Record<ResearchReport["topic"], string> = {
  attractions: "景点与活动",
  weather: "天气",
  hotels: "住宿",
};

const activityKinds: Record<string, string> = {
  walk: "步行游览",
  food: "餐饮",
  garden: "园林",
  museum: "展馆",
  free: "自由活动",
};

/** 展示已保存版本的行程、地点事实、研究证据和提示。 */
export default function SavedPlanResult({ result }: { result: PlanResult }) {
  const { trip, places, research, warnings, reply } = result;
  const placesById = new Map(places.map((place) => [place.id, place]));

  return (
    <div className="saved-result">
      {reply && <p className="saved-reply">{reply}</p>}
      <div className="saved-trip-meta" aria-label="行程概况">
        <span>
          <MapPin size={15} /> {trip.destination}
        </span>
        <span>
          <CalendarDays size={15} /> {trip.days.length} 天行程
        </span>
        <span>
          <UsersRound size={15} /> {trip.travelers} 人同行
        </span>
        <span>
          全团预算 {trip.currency === "CNY" ? "¥" : trip.currency}
          {trip.budget.toLocaleString()}（不含往返大交通）
        </span>
      </div>

      <section aria-labelledby="saved-itinerary-title">
        <h3 className="saved-section-title" id="saved-itinerary-title">
          每日行程
        </h3>
        {trip.days.map((day) => (
          <article className="saved-day" key={day.id}>
            <div className="saved-day-heading">
              <span>
                {day.label} · {day.date}
              </span>
              <h4>{day.title}</h4>
              {day.description && <p>{day.description}</p>}
              <small>路程：{day.distance}</small>
            </div>
            <ol>
              {day.activities.map((activity) => {
                const place = activity.placeId
                  ? placesById.get(activity.placeId)
                  : undefined;
                return (
                  <li key={activity.id}>
                    <time>{activity.time}</time>
                    <div>
                      <strong>{activity.title}</strong>
                      <span className="saved-activity-kind">
                        {activityKinds[activity.kind] ?? activity.kind}
                      </span>
                      {activity.description && <p>{activity.description}</p>}
                      <small>{activity.location}</small>
                      {place && (
                        <small className="saved-activity-source">
                          地图地点：{place.name} ·{" "}
                          {place.source === "amap" ? "高德" : "百度"}
                        </small>
                      )}
                    </div>
                    <span className="saved-activity-cost">
                      {activity.cost === null
                        ? "费用待核实"
                        : `¥${activity.cost.toLocaleString()}`}
                    </span>
                  </li>
                );
              })}
            </ol>
          </article>
        ))}
      </section>

      <section className="saved-facts" aria-labelledby="saved-places-title">
        <h3 className="saved-section-title" id="saved-places-title">
          地点来源 <small>{places.length} 处</small>
        </h3>
        {places.length === 0 ? (
          <p className="saved-empty">本次结果没有保存地图地点。</p>
        ) : (
          <div className="saved-fact-grid">
            {places.map((place) => (
              <article className="saved-fact" key={place.id}>
                <h4>{place.name}</h4>
                <p>{place.address || "地址未提供"}</p>
                <dl>
                  <div>
                    <dt>来源</dt>
                    <dd>{place.source === "amap" ? "高德地图" : "百度地图"}</dd>
                  </div>
                  <div>
                    <dt>坐标</dt>
                    <dd>
                      {place.longitude}, {place.latitude}（
                      {place.coordinate_system}）
                    </dd>
                  </div>
                  <div>
                    <dt>采集时间</dt>
                    <dd>
                      {new Date(place.fetched_at).toLocaleString("zh-CN")}
                    </dd>
                  </div>
                  <div>
                    <dt>地点 ID</dt>
                    <dd>{place.id}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>

      <section
        className="saved-research"
        aria-labelledby="saved-research-title"
      >
        <h3 className="saved-section-title" id="saved-research-title">
          调研资料
        </h3>
        {research.length === 0 ? (
          <p className="saved-empty">本次结果没有保存调研资料。</p>
        ) : (
          research.map((report) => (
            <article className="saved-report" key={report.topic}>
              <h4>{topicNames[report.topic]}</h4>
              <p>{report.summary}</p>
              {report.warnings.length > 0 && (
                <ul>
                  {report.warnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              )}
              {report.evidence.length > 0 && (
                <div className="saved-evidence-list">
                  {report.evidence.map((evidence, index) => (
                    <details key={`${evidence.tool}-${index}`}>
                      <summary>
                        {evidence.tool} ·{" "}
                        {new Date(evidence.fetched_at).toLocaleString("zh-CN")}
                      </summary>
                      <pre>{evidence.content}</pre>
                      {evidence.structured_content !== null && (
                        <>
                          <strong>结构化内容</strong>
                          <pre>
                            {JSON.stringify(
                              evidence.structured_content,
                              null,
                              2,
                            )}
                          </pre>
                        </>
                      )}
                    </details>
                  ))}
                </div>
              )}
            </article>
          ))
        )}
      </section>

      {warnings.length > 0 && (
        <section
          className="saved-warnings"
          aria-labelledby="saved-warnings-title"
        >
          <h3 className="saved-section-title" id="saved-warnings-title">
            待核实事项
          </h3>
          <ul>
            {warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </section>
      )}

      <details className="saved-result-meta">
        <summary>行程数据标识</summary>
        <p>行程 ID：{trip.id}</p>
        <p>结构版本：{trip.schemaVersion}</p>
      </details>
    </div>
  );
}

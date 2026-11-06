import type { Activity } from "../types/trip";

/** 路线示意图的输入与选择事件。 */
interface Props {
  /** 当日活动；仅绘制具有像素坐标的地点。 */
  activities: Activity[];
  /** 当前选中活动 ID，未选择时为 null。 */
  selectedId: string | null;
  /** 选择地点时接收活动 ID 的回调。 */
  onSelect: (id: string) => void;
}

/**
 * 用独立绘制的街区底图展示路线概览，不充当导航地图。
 *
 * @param props - 当日活动、选中标识及选择回调，字段含义见 Props。
 * @returns 仅标记具有 SVG 像素坐标的活动的路线示意图。
 */
export default function RouteMap({ activities, selectedId, onSelect }: Props) {
  const stops = activities.filter((activity) => activity.point);
  return (
    <svg
      className="route-map"
      viewBox="0 0 400 280"
      role="group"
      aria-label="当日路线，点击地点可查看活动"
    >
      <defs>
        <pattern
          id="blocks"
          width="62"
          height="48"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(-14)"
        >
          <rect width="62" height="48" fill="#f4f0e8" />
          <rect x="4" y="4" width="51" height="36" rx="2" fill="#ebe8e0" />
          <path d="M0 44H62M59 0V48" stroke="#fffdf9" strokeWidth="5" />
          <path d="M23 4V39M4 22H54" stroke="#f9f7f1" strokeWidth="2" />
        </pattern>
      </defs>
      <rect width="400" height="340" fill="url(#blocks)" />
      <g fill="#dfe7d2" opacity=".9">
        <path d="M0 5H87L72 76 9 88Z" />
        <path d="M278 0H350L340 82 285 77Z" />
        <path d="M8 242L75 225 90 290 0 310Z" />
        <path d="M306 242L380 230 400 302 323 327Z" />
        <path d="M153 175L184 160 204 200 168 217Z" />
      </g>
      <g fill="none" strokeLinecap="round">
        <path
          d="M110 -10C135 70 84 100 114 170S180 267 153 355"
          stroke="#c4dfe3"
          strokeWidth="12"
        />
        <path
          d="M-20 158C88 130 193 170 430 80"
          stroke="#d6e7e6"
          strokeWidth="8"
        />
        <path d="M331 -10L310 350" stroke="#d1e5e4" strokeWidth="9" />
        <path
          d="M-10 275L421 177M-10 100L410 13"
          stroke="#fffdfa"
          strokeWidth="9"
        />
        <path
          d="M33 -10L160 350M218 -10L220 350"
          stroke="#fffdfa"
          strokeWidth="7"
        />
      </g>
      <g className="street-labels" fill="#93958c" fontSize="9">
        <text x="50" y="120" transform="rotate(-14 50 120)">
          人民路
        </text>
        <text x="289" y="162" transform="rotate(90 289 162)">
          平江河
        </text>
        <text x="120" y="35">
          东北街
        </text>
        <text x="60" y="316">
          十全街
        </text>
      </g>
      {stops.length > 1 && (
        <polyline
          className="route-line"
          points={stops.map((stop) => stop.point!.join(",")).join(" ")}
          fill="none"
          stroke="#78445e"
          strokeWidth="3"
          strokeDasharray="3 6"
          strokeLinecap="round"
        />
      )}
      {stops.map((stop) => (
        <g
          key={stop.id}
          className={`map-stop ${selectedId === stop.id ? "is-selected" : ""}`}
          role="button"
          tabIndex={0}
          aria-label={`查看${stop.title}`}
          aria-pressed={selectedId === stop.id}
          onClick={() => onSelect(stop.id)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onSelect(stop.id);
            }
          }}
        >
          <circle
            cx={stop.point![0]}
            cy={stop.point![1]}
            r="15"
            fill="transparent"
          />
          <circle
            className="marker-halo"
            cx={stop.point![0]}
            cy={stop.point![1]}
            r="11"
            fill="#78445e"
            opacity=".15"
          />
          <circle
            cx={stop.point![0]}
            cy={stop.point![1]}
            r="9"
            fill={selectedId === stop.id ? "var(--wine)" : "var(--paper)"}
            stroke="var(--wine)"
            strokeWidth="1.5"
          />
          <text
            x={stop.point![0]}
            y={stop.point![1] + 3.5}
            textAnchor="middle"
            fontSize="10"
            fontWeight="600"
            fill={selectedId === stop.id ? "var(--paper)" : "var(--wine)"}
          >
            {activities.findIndex((activity) => activity.id === stop.id) + 1}
          </text>
          <text
            x={stop.point![0] + 16}
            y={stop.point![1] + 4}
            fontSize="12"
            fill="#41353b"
            paintOrder="stroke"
            stroke="#fcfaf6"
            strokeWidth="4"
            strokeLinejoin="round"
          >
            {stop.title.split(" · ")[0].replace("漫步", "")}
          </text>
        </g>
      ))}
      <g transform="translate(363 19)" fill="#78445e">
        <path d="M0 0L-5 13 0 10 5 13Z" />
        <text x="-4" y="-5" fontSize="9">
          北
        </text>
      </g>
    </svg>
  );
}

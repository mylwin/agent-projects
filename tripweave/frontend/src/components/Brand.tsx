import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

/**
 * 渲染通往旅行计划列表的品牌链接。
 *
 * @returns 品牌图标与文字链接。
 */
export default function Brand() {
  return (
    <Link className="brand" to="/plans" aria-label="TripWeave · 我的旅行计划">
      <Compass
        className="brand-mark"
        size={34}
        strokeWidth={1.5}
        aria-hidden="true"
      />
      <span>TripWeave</span>
    </Link>
  );
}

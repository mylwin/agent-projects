import { CheckCircleOutlined, RightOutlined, TeamOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { useState } from 'react';

import { CATEGORY_LABELS } from './categoryLabels';
import type { Product } from './types';

interface ProductCardProps {
  product: Product;
  onView: (product: Product) => void;
}

function formatAmount(value: number): string {
  return `¥${value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function ProductCard({ product, onView }: ProductCardProps) {
  const [imageFailed, setImageFailed] = useState(false);

  return (
    <article className="product-card">
      <div className="product-card__main">
        <div className="product-card__media">
          {!imageFailed && product.image_url ? (
            <img
              src={product.image_url}
              alt=""
              loading="lazy"
              referrerPolicy="no-referrer"
              onError={() => setImageFailed(true)}
            />
          ) : (
            <span>{CATEGORY_LABELS[product.category]}</span>
          )}
          <strong>{CATEGORY_LABELS[product.category]}</strong>
        </div>
        <div className="product-card__summary">
          <h3 title={product.name}>{product.name}</h3>
          <p className="product-card__insurer">{product.insurer}</p>
          <p className="product-card__description">{product.description}</p>
        </div>
      </div>
      <div className="product-card__audience">
        <TeamOutlined />
        <span>适合人群：{product.target_group || '不限'}</span>
      </div>
      <ul className="product-card__highlights">
        {product.highlights.slice(0, 3).map((highlight) => (
          <li key={highlight}>
            <CheckCircleOutlined />
            <span>{highlight}</span>
          </li>
        ))}
      </ul>
      <div className="product-card__footer">
        <div>
          <span>年缴保费参考</span>
          {product.min_premium !== null ? (
            <>
              <strong>{formatAmount(product.min_premium)}</strong>
              <small>起</small>
            </>
          ) : (
            <strong className="product-card__price-pending">待定</strong>
          )}
        </div>
        <Button type="link" onClick={() => onView(product)}>
          查看详情 <RightOutlined />
        </Button>
      </div>
    </article>
  );
}

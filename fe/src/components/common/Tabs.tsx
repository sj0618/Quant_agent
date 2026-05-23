import type { ReactNode } from "react";

export interface TabItem<T extends string> {
  id: T;
  label: string;
  count?: number;
}

interface TabsProps<T extends string> {
  items: Array<TabItem<T>>;
  activeId: T;
  onChange: (id: T) => void;
  rightSlot?: ReactNode;
}

export function Tabs<T extends string>({ items, activeId, onChange, rightSlot }: TabsProps<T>) {
  return (
    <div className="tabs">
      <div className="tabs__list">
        {items.map((item) => (
          <button
            aria-pressed={item.id === activeId}
            className={["tabs__item", item.id === activeId ? "tabs__item--active" : ""].filter(Boolean).join(" ")}
            key={item.id}
            onClick={() => onChange(item.id)}
            type="button"
          >
            <span>{item.label}</span>
            {typeof item.count === "number" ? <span className="tabs__count">{item.count}</span> : null}
          </button>
        ))}
      </div>
      {rightSlot ? <div className="tabs__meta">{rightSlot}</div> : null}
    </div>
  );
}

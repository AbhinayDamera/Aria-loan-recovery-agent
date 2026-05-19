"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import type { EmotionPoint } from "@/lib/types";

export function EmotionChart({ data }: { data: EmotionPoint[] }) {
  return (
    <div className="h-44 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: -16 }}>
          <defs>
            <linearGradient id="stressFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#d85a30" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#d85a30" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#292524" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="t"
            tickFormatter={formatT}
            stroke="#57534e"
            fontSize={11}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            stroke="#57534e"
            fontSize={11}
            tickLine={false}
            axisLine={false}
            width={40}
          />
          <Area
            type="monotone"
            dataKey="score"
            stroke="#e07a5f"
            strokeWidth={2}
            fill="url(#stressFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function formatT(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

import { BadgeCheck, Check, Fuel, Gauge, QrCode, Scale, Thermometer } from "lucide-react";

const INSTRUMENTS = [
  { icon: Scale, label: "Weighing scale" },
  { icon: Fuel, label: "Fuel dispenser" },
  { icon: Gauge, label: "Water meter" },
  { icon: Thermometer, label: "Thermometer" },
];

export function HeroIllustration() {
  return (
    <div className="relative mx-auto w-full max-w-md pt-6 pb-8 sm:max-w-lg">
      <div className="relative aspect-square rounded-[2.5rem] bg-gradient-to-br from-primary/10 via-accent/70 to-success/15 ring-1 ring-border">
        <div className="grid h-full grid-cols-2 gap-4 p-8 sm:p-10">
          {INSTRUMENTS.map(({ icon: Icon, label }) => (
            <div
              key={label}
              className="flex flex-col items-center justify-center gap-2 rounded-2xl bg-card/90 p-4 text-center shadow-sm ring-1 ring-border backdrop-blur"
            >
              <Icon className="size-8 text-primary" aria-hidden="true" />
              <span className="text-xs font-medium text-muted-foreground">{label}</span>
            </div>
          ))}
        </div>

        <div className="absolute -top-5 right-2 flex w-32 flex-col items-center gap-1.5 rounded-xl bg-card p-3 text-center shadow-lg ring-1 ring-border sm:-right-6">
          <span className="flex size-9 items-center justify-center rounded-full bg-success/15 text-success">
            <BadgeCheck className="size-5" aria-hidden="true" />
          </span>
          <span className="text-xs font-semibold tracking-wide text-foreground">VERIFIED</span>
        </div>

        <div className="absolute -bottom-5 left-2 flex items-center gap-2 rounded-xl bg-card p-3 shadow-lg ring-1 ring-border sm:-left-6">
          <QrCode className="size-9 text-foreground" aria-hidden="true" />
          <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-success text-success-foreground">
            <Check className="size-3" aria-hidden="true" />
          </span>
        </div>
      </div>
    </div>
  );
}

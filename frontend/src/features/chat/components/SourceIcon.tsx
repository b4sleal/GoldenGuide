import { BookOpenIcon, CalendarDaysIcon, FileTextIcon, GlobeIcon, type LucideIcon } from "lucide-react";

const SOURCE_ICONS: Record<string, LucideIcon> = {
  courses: BookOpenIcon,
  course_terms: CalendarDaysIcon,
  loris_registration: CalendarDaysIcon,
  doc: FileTextIcon,
};

/** An icon for the kind of source (course record, registration, document); a globe for web pages. */
export function SourceIcon({ sourceType, className }: { sourceType: string | null | undefined; className?: string }) {
  const Icon = (sourceType && SOURCE_ICONS[sourceType]) || GlobeIcon;
  return <Icon className={className} aria-hidden />;
}

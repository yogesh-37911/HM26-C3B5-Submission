import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export type Lang = "en" | "kn";

// Explicit translations for interface chrome, per the brief:
// "Do not machine-translate every database field. UI labels should have
// explicit translations." Complaint content (titles/descriptions) stays in
// whatever language the citizen wrote it in; category names carry their own
// name_kn from the backend.
const dict = {
  en: {
    appName: "Mysuru CivicPulse",
    tagline: "From complaint to closure - before civic issues are forgotten.",
    reportIssue: "Report an Issue",
    trackComplaint: "Track Complaint",
    publicDashboard: "Public Dashboard",
    officerLogin: "Officer Login",
    login: "Log in",
    logout: "Log out",
    email: "Email",
    password: "Password",
    myComplaints: "My complaints",
    submit: "Submit",
    submitting: "Submitting...",
    title: "Title",
    description: "Description",
    category: "Category",
    landmark: "Landmark / nearby place",
    location: "Location",
    useMyLocation: "Use my location",
    checking: "Checking for duplicates...",
    possibleDuplicate: "Possible duplicate found nearby",
    followExisting: "Follow existing complaint",
    submitSeparately: "Submit as separate issue",
    priority: "Priority",
    risk: "Neglect risk",
    status: "Status",
    verification: "Verification",
    whyThisScore: "Why this score?",
    recommendedAction: "Recommended action",
    timeline: "Timeline",
    assignedTo: "Assigned",
    unassigned: "Unassigned",
    addFollowup: "Add follow-up",
    requestReopen: "Report issue remains unresolved",
    slaRemaining: "SLA remaining",
    slaOverdue: "Overdue",
    officerQueue: "Complaint queue",
    fieldTasks: "My tasks",
    publicOverview: "City overview",
    wardExplain: "Why is this ward behind?",
    demoConsole: "Demo console",
    jurisdictionVersions: "Jurisdiction versions",
    surgeSimulation: "Dasara surge simulation",
    demoDataset: "Demo dataset - synthetic data for HackMysuru demonstration.",
  },
  kn: {
    appName: "ಮೈಸೂರು ಸಿವಿಕ್‌ಪಲ್ಸ್",
    tagline: "ದೂರಿನಿಂದ ಪರಿಹಾರದವರೆಗೆ - ನಾಗರಿಕ ಸಮಸ್ಯೆಗಳು ಮರೆಯಾಗುವ ಮೊದಲು.",
    reportIssue: "ಸಮಸ್ಯೆ ವರದಿ ಮಾಡಿ",
    trackComplaint: "ದೂರು ಟ್ರ್ಯಾಕ್ ಮಾಡಿ",
    publicDashboard: "ಸಾರ್ವಜನಿಕ ಡ್ಯಾಶ್‌ಬೋರ್ಡ್",
    officerLogin: "ಅಧಿಕಾರಿ ಲಾಗಿನ್",
    login: "ಲಾಗ್ ಇನ್",
    logout: "ಲಾಗ್ ಔಟ್",
    email: "ಇಮೇಲ್",
    password: "ಪಾಸ್‌ವರ್ಡ್",
    myComplaints: "ನನ್ನ ದೂರುಗಳು",
    submit: "ಸಲ್ಲಿಸಿ",
    submitting: "ಸಲ್ಲಿಸಲಾಗುತ್ತಿದೆ...",
    title: "ಶೀರ್ಷಿಕೆ",
    description: "ವಿವರಣೆ",
    category: "ವರ್ಗ",
    landmark: "ಹತ್ತಿರದ ಸ್ಥಳ",
    location: "ಸ್ಥಳ",
    useMyLocation: "ನನ್ನ ಸ್ಥಳ ಬಳಸಿ",
    checking: "ನಕಲಿ ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ...",
    possibleDuplicate: "ಹತ್ತಿರದಲ್ಲಿ ಸಂಭಾವ್ಯ ನಕಲಿ ದೂರು ಪತ್ತೆಯಾಗಿದೆ",
    followExisting: "ಈಗಿರುವ ದೂರನ್ನು ಅನುಸರಿಸಿ",
    submitSeparately: "ಪ್ರತ್ಯೇಕ ಸಮಸ್ಯೆಯಾಗಿ ಸಲ್ಲಿಸಿ",
    priority: "ಆದ್ಯತೆ",
    risk: "ನಿರ್ಲಕ್ಷ್ಯ ಅಪಾಯ",
    status: "ಸ್ಥಿತಿ",
    verification: "ಪರಿಶೀಲನೆ",
    whyThisScore: "ಈ ಸ್ಕೋರ್ ಏಕೆ?",
    recommendedAction: "ಶಿಫಾರಸು ಮಾಡಿದ ಕ್ರಮ",
    timeline: "ಟೈಮ್‌ಲೈನ್",
    assignedTo: "ನಿಯೋಜಿಸಲಾಗಿದೆ",
    unassigned: "ನಿಯೋಜಿಸಿಲ್ಲ",
    addFollowup: "ಫಾಲೋ-ಅಪ್ ಸೇರಿಸಿ",
    requestReopen: "ಸಮಸ್ಯೆ ಇನ್ನೂ ಬಗೆಹರಿದಿಲ್ಲ ಎಂದು ವರದಿ ಮಾಡಿ",
    slaRemaining: "SLA ಬಾಕಿ",
    slaOverdue: "ಮಿತಿ ಮೀರಿದೆ",
    officerQueue: "ದೂರು ಸರತಿ",
    fieldTasks: "ನನ್ನ ಕಾರ್ಯಗಳು",
    publicOverview: "ನಗರ ಅವಲೋಕನ",
    wardExplain: "ಈ ವಾರ್ಡ್ ಏಕೆ ಹಿಂದುಳಿದಿದೆ?",
    demoConsole: "ಡೆಮೊ ಕನ್ಸೋಲ್",
    jurisdictionVersions: "ವ್ಯಾಪ್ತಿ ಆವೃತ್ತಿಗಳು",
    surgeSimulation: "ದಸರಾ ಉಲ್ಬಣ ಸಿಮ್ಯುಲೇಶನ್",
    demoDataset: "ಡೆಮೊ ಡೇಟಾಸೆಟ್ - ಹ್ಯಾಕ್‌ಮೈಸೂರು ಪ್ರದರ್ಶನಕ್ಕಾಗಿ ಸಿಂಥೆಟಿಕ್ ಡೇಟಾ.",
  },
} as const;

// Both language objects share identical keys but TypeScript infers each as
// its own literal-string type from `as const`; widen to a plain string
// record so `t` can hold whichever language is active.
type Dict = Record<keyof typeof dict.en, string>;

const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: Dict } | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>((localStorage.getItem("civicpulse.lang") as Lang) || "en");
  const setLangPersist = (l: Lang) => {
    localStorage.setItem("civicpulse.lang", l);
    setLang(l);
  };
  const t = useMemo(() => dict[lang], [lang]);
  return (
    <LangContext.Provider value={{ lang, setLang: setLangPersist, t }}>
      <div lang={lang} className={lang === "kn" ? "lang-kn" : undefined}>
        {children}
      </div>
    </LangContext.Provider>
  );
}

export function useLang() {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useLang must be used within LangProvider");
  return ctx;
}

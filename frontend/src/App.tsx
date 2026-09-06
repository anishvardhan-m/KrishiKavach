// KrishiKavach — voice-first farmer UI (SIH26131 vertical slice).
//
// Flow:
//   1. App opens → immediate voice greeting.
//   2. Main screen with 5 large color-coded buttons.
//   3. Every action follows the reusable pattern:
//        prompt → "Please speak. I am listening." → listen → interpret → respond.

import { useCallback, useEffect, useState } from "react"
import { ActionButton } from "./components/ActionButton"
import { VoiceBanner } from "./components/VoiceBanner"
import { ResultCard } from "./components/ResultCard"
import { RiskCard } from "./components/RiskCard"
import { ExpertCard } from "./components/ExpertCard"
import { useVoiceController } from "./hooks/useVoiceController"
import { usePhotoCapture } from "./hooks/usePhotoCapture"
import { listOutbreaks, predictImage } from "./services/api"
import type { CaseCreateResponse, DiseaseReport } from "./types"

type Screen =
  | { name: "home" }
  | { name: "photo-preview" }
  | { name: "predicting" }
  | { name: "result"; data: CaseCreateResponse }
  | { name: "risk"; reports: DiseaseReport[]; loading: boolean; error: string | null }
  | { name: "expert" }
  | { name: "listening-prompt" }

export default function App() {
  const voice = useVoiceController("en-IN")
  const photo = usePhotoCapture()

  const [screen, setScreen] = useState<Screen>({ name: "home" })
  const [bannerMessage, setBannerMessage] = useState<string>("")
  const [predictError, setPredictError] = useState<string | null>(null)
  const [hasGreeted, setHasGreeted] = useState(false)

  // ---------- Voice helpers ----------
  const speak = useCallback(
    async (text: string) => {
      await voice.controller.speak(text)
    },
    [voice.controller],
  )

  // ---------- Greeting on first mount ----------
  useEffect(() => {
    if (hasGreeted) return
    setHasGreeted(true)
    const greeting =
      "Welcome to Krishi Kavach. I am your farming assistant. " +
      "Tap the green button to take a photo of your crop. " +
      "I will tell you what is wrong and what to do."
    setBannerMessage(greeting)
    speak(greeting).catch(() => {
      /* silent — text is still visible */
    })
    // Warn up front if mic is not available
    if (!voice.controller.isRecognitionSupported()) {
      setBannerMessage(
        greeting +
          " (Microphone not available on this device — voice input disabled.)",
      )
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---------- Action: Take Photo ----------
  const handleTakePhoto = useCallback(async () => {
    await speak(
      "Please take a clear photo of the sick leaf or plant. " +
        "Make sure the sun is on it, not behind it.",
    )
    photo.openCamera()
  }, [speak, photo])

  // ---------- After photo is chosen ----------
  const handlePredict = useCallback(async () => {
    if (!photo.pendingFile) return
    setPredictError(null)
    setScreen({ name: "predicting" })
    setBannerMessage("Looking at the photo...")
    await speak("Looking at the photo. Please wait.")
    try {
      const result = await predictImage(photo.pendingFile)
      setScreen({ name: "result", data: result })
      // Speak the result
      const summary =
        result.prediction.disease +
        (result.prediction.crop && result.prediction.crop !== "Unknown"
          ? " on " + result.prediction.crop
          : "") +
        ". " +
        result.prediction.recommendation_text
      setBannerMessage(summary)
      await speak(summary)
    } catch (e: any) {
      const msg = e?.message || "Could not reach the server."
      setPredictError(msg)
      setScreen({ name: "photo-preview" })
      setBannerMessage("Sorry, something went wrong. " + msg)
      await speak("Sorry, something went wrong. " + msg)
    }
  }, [photo.pendingFile, speak])

  // ---------- Listen-again / result ----------
  const handleSpeakResultAgain = useCallback(async () => {
    if (screen.name !== "result") return
    const p = screen.data.prediction
    const summary =
      p.disease + ". " + p.recommendation_text
    setBannerMessage(summary)
    await speak(summary)
  }, [screen, speak])

  // ---------- Done from result → back home ----------
  const handleResultDone = useCallback(() => {
    photo.reset()
    setScreen({ name: "home" })
    setBannerMessage("Done. What would you like to do next?")
    speak("Done. What would you like to do next?").catch(() => {})
  }, [speak, photo])

  // ---------- Action: What should I do? ----------
  const handleWhatToDo = useCallback(async () => {
    if (screen.name === "result") {
      handleSpeakResultAgain()
      return
    }
    // Generic advice — voice interaction pattern
    await speak(
      "Tell me what you see. Is the leaf yellow, brown, or spotted? " +
        "I will listen and tell you what to do.",
    )
    const reply = await voice.controller.promptAndListen()
    if (!reply) {
      const msg = "I did not hear anything. Please try again."
      setBannerMessage(msg)
      await speak(msg)
      return
    }
    setBannerMessage("You said: " + reply)
    // Map common farmer phrases to simple guidance
    const text = reply.toLowerCase()
    let response =
      "I heard you. For any plant disease, the safest first step is to " +
      "remove the worst affected leaves and take a clear photo so I can " +
      "give exact advice."
    if (text.includes("yellow")) {
      response =
        "Yellow leaves often mean a nutrient problem or over-watering. " +
        "Check the soil moisture and reduce watering for a few days. " +
        "If the problem spreads, tap the green button to send me a photo."
    } else if (text.includes("spot") || text.includes("brown")) {
      response =
        "Spots or brown patches usually mean a fungal disease. " +
        "Remove the affected leaves and avoid watering from above. " +
        "Take a photo and I will tell you the exact treatment."
    } else if (text.includes("insect") || text.includes("pest") || text.includes("bug")) {
      response =
        "For insects, neem oil spray at five millilitres per litre of " +
        "water works well for most pests. Spray in the evening. " +
        "Send me a photo if it is a new pest."
    }
    setBannerMessage(response)
    await speak(response)
  }, [screen, speak, voice.controller, handleSpeakResultAgain])

  // ---------- Action: Nearby Risk ----------
  const handleNearbyRisk = useCallback(async () => {
    setScreen({ name: "risk", reports: [], loading: true, error: null })
    setBannerMessage("Looking for nearby disease alerts...")
    await speak("Looking for nearby disease alerts. Please wait.")
    try {
      const reports = await listOutbreaks()
      setScreen({ name: "risk", reports, loading: false, error: null })
      if (reports.length === 0) {
        const msg =
          "Good news. No disease outbreaks have been reported in your area right now."
        setBannerMessage(msg)
        await speak(msg)
      } else {
        const first = reports[0]
        const msg = `${reports.length} outbreak report${
          reports.length === 1 ? "" : "s"
        } nearby. The most recent: ${first.disease_type || "a disease"} in ${
          first.district || "your area"
        } at ${
          RISK_LABEL[first.risk_level || "medium"]
        }.`
        setBannerMessage(msg)
        await speak(msg)
      }
    } catch (e: any) {
      const msg = e?.message || "Could not load outbreak data."
      setScreen({ name: "risk", reports: [], loading: false, error: msg })
      setBannerMessage("Sorry, " + msg)
      await speak("Sorry. " + msg)
    }
  }, [speak])

  // ---------- Action: Expert Help ----------
  const handleExpertHelp = useCallback(async () => {
    setScreen({ name: "expert" })
    const msg =
      "An expert can look at your photo. Call the Krishi Vigyan Kendra " +
      "helpline at 1800-103-AGRI. It is free and open every day from " +
      "six in the morning until ten at night."
    setBannerMessage(msg)
    await speak(msg)
  }, [speak])

  // ---------- Action: Listen Again (re-speak current banner) ----------
  const handleListenAgain = useCallback(async () => {
    if (!bannerMessage) {
      const msg = "There is nothing new to say right now."
      setBannerMessage(msg)
      await speak(msg)
      return
    }
    await speak(bannerMessage)
  }, [bannerMessage, speak])

  // ---------- File input change → preview then predict ----------
  const onFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      photo.onFileSelected(e)
    },
    [photo],
  )

  useEffect(() => {
    if (photo.pendingFile && screen.name === "home") {
      setScreen({ name: "photo-preview" })
      const msg = "I see the photo. Tap the green button at the bottom to send it for analysis."
      setBannerMessage(msg)
      speak(msg)
    }
  }, [photo.pendingFile, screen.name, speak])

  // ---------- Render ----------
  return (
    <div className="app">
      <header className="app-header">
        <div className="app-title">
          <span className="leaf" aria-hidden="true">🌿</span>
          <span>KrishiKavach</span>
        </div>
        <span className="demo-badge">SIH DEMO</span>
      </header>

      <VoiceBanner
        status={voice.status}
        interim={voice.interim}
        message={bannerMessage}
      />

      {screen.name === "home" && (
        <div className="actions">
          <ActionButton
            color="green"
            icon="📸"
            label="Take Photo"
            sublabel="Photo of your sick crop"
            onClick={handleTakePhoto}
            disabled={!photo.openCamera}
          />
          <ActionButton
            color="blue"
            icon="❓"
            label="What should I do?"
            sublabel="Ask by speaking"
            onClick={handleWhatToDo}
            disabled={!voice.controller.isRecognitionSupported()}
          />
          <ActionButton
            color="orange"
            icon="⚠️"
            label="Nearby Risk"
            sublabel="Disease alerts in your area"
            onClick={handleNearbyRisk}
          />
          <ActionButton
            color="red"
            icon="🆘"
            label="Expert Help"
            sublabel="Call an agriculture expert"
            onClick={handleExpertHelp}
          />
          <ActionButton
            color="purple"
            icon="🔊"
            label="Listen Again"
            sublabel="Repeat the last message"
            onClick={handleListenAgain}
          />
        </div>
      )}

      {screen.name === "photo-preview" && (
        <>
          {photo.previewUrl && (
            <div className="preview-wrap">
              <img
                className="preview-img"
                src={photo.previewUrl}
                alt="Selected crop"
              />
            </div>
          )}
          {predictError && <div className="error">{predictError}</div>}
          <div className="actions">
            <ActionButton
              color="green"
              icon="🔍"
              label="Send for Analysis"
              sublabel="Find out what is wrong"
              onClick={handlePredict}
            />
            <ActionButton
              color="ghost"
              icon="📷"
              label="Retake Photo"
              onClick={() => {
                photo.reset()
                setScreen({ name: "home" })
              }}
            />
            <ActionButton
              color="blue"
              icon="❓"
              label="What should I do?"
              sublabel="Ask by speaking"
              onClick={handleWhatToDo}
              disabled={!voice.controller.isRecognitionSupported()}
            />
          </div>
        </>
      )}

      {screen.name === "predicting" && (
        <div className="card">
          <div className="loading">
            <div className="spinner" />
            <div>Looking at your photo...</div>
          </div>
        </div>
      )}

      {screen.name === "result" && (
        <>
          <ResultCard
            prediction={screen.data.prediction}
            onSpeakAgain={handleSpeakResultAgain}
            onDone={handleResultDone}
          />
          {screen.data.prediction.uncertainty_flag && (
            <ActionButton
              color="red"
              icon="🆘"
              label="Expert Help"
              sublabel="Because we are not fully sure"
              onClick={handleExpertHelp}
            />
          )}
        </>
      )}

      {screen.name === "risk" && (
        <RiskCard
          reports={screen.reports}
          loading={screen.loading}
          error={screen.error}
          onDone={() => setScreen({ name: "home" })}
          onSpeak={async () => {
            if (screen.reports.length === 0) {
              await speak("No outbreaks reported in your area.")
              return
            }
            const lines = screen.reports
              .slice(0, 3)
              .map((r) => {
                return `${r.disease_type || "a disease"} in ${
                  r.district || "your area"
                }, ${RISK_LABEL[r.risk_level || "medium"]}, ${
                  r.affected_farms
                } farms affected.`
              })
              .join(" ")
            setBannerMessage(lines)
            await speak(lines)
          }}
        />
      )}

      {screen.name === "expert" && (
        <ExpertCard
          onDone={() => setScreen({ name: "home" })}
          onSpeak={async () => {
            const msg =
              "Call 1800-103-AGRI. It is the Krishi Vigyan Kendra helpline, " +
              "free, every day from six AM to ten PM."
            setBannerMessage(msg)
            await speak(msg)
          }}
        />
      )}

      {/* Hidden inputs for camera + gallery */}
      <input
        ref={photo.cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={onFileChange}
        style={{ display: "none" }}
        aria-hidden="true"
      />
      <input
        ref={photo.galleryInputRef}
        type="file"
        accept="image/*"
        onChange={onFileChange}
        style={{ display: "none" }}
        aria-hidden="true"
      />

      <footer className="app-footer">
        <div>KrishiKavach — SIH26131</div>
        <div>Voice-first crop-health assistant for Maharashtra farmers</div>
        <div style={{ marginTop: 6 }}>
          Predictions use the demo rule-based service (clearly marked DEMO).
        </div>
      </footer>
    </div>
  )
}

const RISK_LABEL: Record<string, string> = {
  low: "low risk",
  medium: "moderate risk",
  high: "high risk",
  critical: "critical",
}

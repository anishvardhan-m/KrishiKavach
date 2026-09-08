// KrishiKavach — voice-first farmer UI (SIH26131 vertical slice).
//
// Flow:
//   1. App opens → immediate voice greeting in the chosen language.
//   2. Main screen with 5 large color-coded buttons.
//   3. Every action follows the reusable pattern:
//        prompt → "Please speak. I am listening." → listen → interpret → respond.

import { useCallback, useEffect, useState } from "react"
import { ActionButton } from "./components/ActionButton"
import { VoiceBanner } from "./components/VoiceBanner"
import { ResultCard } from "./components/ResultCard"
import { RiskCard } from "./components/RiskCard"
import { EarlyWarningCard } from "./components/EarlyWarningCard"
import { ExpertCard } from "./components/ExpertCard"
import { OfficerDashboard } from "./components/OfficerDashboard"
import { ExpertReviewQueue } from "./components/ExpertReviewQueue"
import { FollowUpCard } from "./components/FollowUpCard"
import { LanguagePicker } from "./components/LanguagePicker"
import { useVoiceController } from "./hooks/useVoiceController"
import { usePhotoCapture } from "./hooks/usePhotoCapture"
import { listOutbreaks, predictImage } from "./services/api"
import type { CaseCreateResponse, DiseaseReport } from "./types"
import type { VoiceLanguage } from "./services/voice"
import { t } from "./i18n/strings"

// Welcome message — multi-sentence guided intro for the farmer home screen.
function getWelcomeText(language: VoiceLanguage): string {
  return t("welcome_voice_intro", language)
}

type Screen =
  | { name: "home" }
  | { name: "photo-preview" }
  | { name: "predicting" }
  | { name: "result"; data: CaseCreateResponse }
  | { name: "risk"; reports: DiseaseReport[]; loading: boolean; error: string | null }
  | { name: "expert" }
  | { name: "officer" }
  | { name: "expert-review" }
  | { name: "follow-up" }

const DEFAULT_LANGUAGE: VoiceLanguage = "hi-IN"

export default function App() {
  const [language, setLanguage] = useState<VoiceLanguage>(DEFAULT_LANGUAGE)
  const voice = useVoiceController(language)
  const photo = usePhotoCapture()

  const [screen, setScreen] = useState<Screen>({ name: "home" })
  const [bannerMessage, setBannerMessage] = useState<string>("")
  const [predictError, setPredictError] = useState<string | null>(null)
  const [hasGreeted, setHasGreeted] = useState(false)
  // Autoplay retry: true when the browser blocked the greeting audio and the
  // farmer needs to tap a button to enable it.
  const [greetingAutoplayBlocked, setGreetingAutoplayBlocked] = useState(false)

  const speak = useCallback(
    async (text: string) => {
      await voice.controller.speak(text)
    },
    [voice.controller],
  )

  // Play the welcome voice intro once on mount. Visible banner text remains
  // `greeting_initial` (per spec — farmers may be in noisy environments).
  // The spoken text is the longer `welcome_voice_intro` which explains each
  // color-coded button.
  const playWelcome = useCallback(async () => {
    const intro = getWelcomeText(language)
    try {
      await speak(intro)
      setGreetingAutoplayBlocked(false)
    } catch (e) {
      // speak() never throws to here; the controller absorbs errors.
      // We surface autoplay-block via the controller's `isAutoplayBlocked()`
      // after the call returns.
      if (voice.controller.isAutoplayBlocked()) {
        setGreetingAutoplayBlocked(true)
      }
    }
  }, [language, speak, voice.controller])

  // ---------- Greeting on first mount ----------
  useEffect(() => {
    if (hasGreeted) return
    setHasGreeted(true)
    const greeting = t("greeting_initial", language)
    setBannerMessage(greeting)
    if (!voice.controller.isRecognitionSupported()) {
      setBannerMessage(
        greeting + "  (" + t("voice_mic_unavailable", language) + ")",
      )
    }
    // Try autoplay once. If blocked, the controller records the error and
    // we show the retry prompt below. We do NOT repeatedly retry — that's
    // left to the user's first tap.
    void playWelcome()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // If the language changes while the welcome banner is showing, re-attempt
  // playback so the user hears the new language. Skip on every other screen
  // — only the home page triggers the welcome voice.
  useEffect(() => {
    if (!hasGreeted) return
    if (screen.name !== "home") return
    void playWelcome()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language])

  // Clear retry prompt when navigating away from home so it doesn't bleed
  // into other screens (Officer Dashboard, Expert Review Queue, etc).
  useEffect(() => {
    if (screen.name !== "home") setGreetingAutoplayBlocked(false)
  }, [screen.name])

  // ---------- Action: Take Photo ----------
  const handleTakePhoto = useCallback(async () => {
    const msg =
      language === "hi-IN"
        ? "कृपया पौधे की साफ़ फोटो लें। सूरज पौधे पर हो, पीछे नहीं।"
        : "Please take a clear photo of the sick leaf or plant. Make sure the sun is on it, not behind it."
    photo.openCamera()
    void speak(msg)
  }, [speak, photo, language])

  // ---------- After photo is chosen ----------
  const handlePredict = useCallback(async () => {
    if (!photo.pendingFile) return
    setPredictError(null)
    setScreen({ name: "predicting" })
    const loadingMsg = t("loading_photo", language)
    setBannerMessage(loadingMsg)
    await speak(loadingMsg)
    try {
      const result = await predictImage(photo.pendingFile, undefined, undefined, undefined, language)
      setScreen({ name: "result", data: result })
      const summary =
        result.prediction.disease +
        (result.prediction.crop && result.prediction.crop !== "Unknown"
          ? " — " + result.prediction.crop
          : "") +
        ". " +
        result.prediction.recommendation_text
      // If the backend provided an Early Warning (risk forecast), append a
      // short farmer-facing warning so the same info is spoken aloud.
      let summaryToSpeak = summary
      if (result.risk_forecast) {
        const f = result.risk_forecast
        const levelWord =
          f.risk_level === "critical"
            ? "गंभीर"
            : f.risk_level === "high"
            ? "उच्च जोखिम"
            : f.risk_level === "medium"
            ? "मध्यम जोखिम"
            : "कम जोखिम"
        summaryToSpeak +=
          (language === "hi-IN"
            ? ` सावधानी: आपके क्षेत्र में ${levelWord} है। `
            : ` Warning: there is ${levelWord} risk in your area. `) +
          f.recommended_action
      }
      setBannerMessage(summaryToSpeak)
      await speak(summaryToSpeak)
    } catch (e: any) {
      const msg = e?.message || "Could not reach the server."
      setPredictError(msg)
      setScreen({ name: "photo-preview" })
      const errMsg =
        language === "hi-IN"
          ? "माफ़ कीजिए, कुछ गलत हो गया। " + msg
          : "Sorry, something went wrong. " + msg
      setBannerMessage(errMsg)
      await speak(errMsg)
    }
  }, [photo.pendingFile, speak, language])

  // ---------- Listen-again / result ----------
  const handleSpeakResultAgain = useCallback(async () => {
    if (screen.name !== "result") return
    const p = screen.data.prediction
    const summary = p.disease + ". " + p.recommendation_text
    setBannerMessage(summary)
    await speak(summary)
  }, [screen, speak])

  // ---------- Done from result → back home ----------
  const handleResultDone = useCallback(() => {
    photo.reset()
    setScreen({ name: "home" })
    const msg =
      language === "hi-IN"
        ? "हो गया। अब आगे क्या करना चाहेंगे?"
        : "Done. What would you like to do next?"
    setBannerMessage(msg)
    speak(msg).catch(() => {})
  }, [speak, photo, language])

  // ---------- Action: What should I do? ----------
  const handleWhatToDo = useCallback(async () => {
    if (screen.name === "result") {
      handleSpeakResultAgain()
      return
    }
    const prompt =
      language === "hi-IN"
        ? "बताइए आप क्या देख रहे हैं। पत्ता पीला है, भूरा है, या धब्बेदार है? मैं सुनकर बताऊँगा क्या करना है।"
        : "Tell me what you see. Is the leaf yellow, brown, or spotted? I will listen and tell you what to do."
    await speak(prompt)
    const reply = await voice.controller.promptAndListen()
    if (!reply) {
      const msg =
        language === "hi-IN"
          ? "मुझे कुछ सुनाई नहीं दिया। कृपया फिर कोशिश कीजिए।"
          : "I did not hear anything. Please try again."
      setBannerMessage(msg)
      await speak(msg)
      return
    }
    setBannerMessage(
      (language === "hi-IN" ? "आपने कहा: " : "You said: ") + reply,
    )
    const text = reply.toLowerCase()
    let response =
      language === "hi-IN"
        ? "मैंने आपकी बात सुनी। किसी भी पौधे रोग के लिए सबसे सुरक्षित पहला कदम है सबसे ज़्यादा प्रभावित पत्ते हटा दें और एक साफ़ फोटो लेकर मुझे भेजें, ताकि मैं सही सलाह दे सकूँ।"
        : "I heard you. For any plant disease, the safest first step is to remove the worst affected leaves and take a clear photo so I can give exact advice."

    if (text.includes("yellow") || text.includes("पीला") || text.includes("피")) {
      response =
        language === "hi-IN"
          ? "पीले पत्ते अक्सर पोषण की कमी या अधिक पानी का संकेत हैं। मिट्टी की नमी जाँचें और कुछ दिन पानी कम दें। अगर समस्या बढ़े तो हरा बटन दबाकर फोटो भेजें।"
          : "Yellow leaves often mean a nutrient problem or over-watering. Check the soil moisture and reduce watering for a few days. If the problem spreads, tap the green button to send me a photo."
    } else if (text.includes("spot") || text.includes("brown") || text.includes("धब्बा") || text.includes("भूरा")) {
      response =
        language === "hi-IN"
          ? "धब्बे या भूरे हिस्से आमतौर पर फफूंद रोग होते हैं। प्रभावित पत्ते हटा दें और ऊपर से पानी ना दें। एक फोटो लेकर मुझे भेजें, मैं सही दवाई बताऊँगा।"
          : "Spots or brown patches usually mean a fungal disease. Remove the affected leaves and avoid watering from above. Take a photo and I will tell you the exact treatment."
    } else if (
      text.includes("insect") ||
      text.includes("pest") ||
      text.includes("bug") ||
      text.includes("कीट")
    ) {
      response =
        language === "hi-IN"
          ? "कीटों के लिए 5 मिली नीम तेल प्रति लीटर पानी में मिलाकर शाम को छिड़कें। अगर यह नया कीट है तो मुझे फोटो भेजें।"
          : "For insects, neem oil spray at five millilitres per litre of water works well for most pests. Spray in the evening. Send me a photo if it is a new pest."
    }
    setBannerMessage(response)
    await speak(response)
  }, [screen, speak, voice.controller, language, handleSpeakResultAgain])

  // ---------- Action: Nearby Risk ----------
  const handleNearbyRisk = useCallback(async () => {
    setScreen({ name: "risk", reports: [], loading: true, error: null })
    const loadingMsg = t("loading_outbreaks", language)
    setBannerMessage(loadingMsg)
    await speak(loadingMsg)
    try {
      const reports = await listOutbreaks()
      setScreen({ name: "risk", reports, loading: false, error: null })
      if (reports.length === 0) {
        const msg = t("no_outbreaks", language)
        setBannerMessage(msg)
        await speak(msg)
      } else {
        const first = reports[0]
        const riskLabel = RISK_LABEL[first.risk_level || "medium"]
        const msg =
          language === "hi-IN"
            ? `${reports.length} रोग रिपोर्ट आस-पास मिली। सबसे पहली: ${first.disease_type || "एक रोग"} ${first.district || "आपके क्षेत्र"} में, ${riskLabel}।`
            : `${reports.length} outbreak report${reports.length === 1 ? "" : "s"} nearby. The most recent: ${first.disease_type || "a disease"} in ${first.district || "your area"} at ${riskLabel}.`
        setBannerMessage(msg)
        await speak(msg)
      }
    } catch (e: any) {
      const msg = e?.message || "Could not load outbreak data."
      setScreen({ name: "risk", reports: [], loading: false, error: msg })
      const errMsg =
        language === "hi-IN"
          ? "माफ़ कीजिए। " + msg
          : "Sorry. " + msg
      setBannerMessage(errMsg)
      await speak(errMsg)
    }
  }, [speak, language])

  // ---------- Action: Follow-up ----------
  const handleCheckCrop = useCallback(async () => {
    setScreen({ name: "follow-up" })
    const msg =
      language === "hi-IN"
        ? "आपकी फसल कैसी है? कृपया अपना हाल बताएँ।"
        : "How is your crop? Please tell us the outcome."
    setBannerMessage(msg)
    await speak(msg)
  }, [speak, language])

  // ---------- Action: Expert Help ----------
  const handleExpertHelp = useCallback(async () => {
    setScreen({ name: "expert" })
    const msg =
      language === "hi-IN"
        ? "एक विशेषज्ञ आपकी फोटो देख सकते हैं। कृषि विज्ञान केंद्र हेल्पलाइन 1800-103-AGRI पर कॉल करें। यह मुफ़्त है और रोज़ सुबह 6 बजे से रात 10 बजे तक खुली रहती है।"
        : "An expert can look at your photo. Call the Krishi Vigyan Kendra helpline at 1800-103-AGRI. It is free and open every day from six in the morning until ten at night."
    setBannerMessage(msg)
    await speak(msg)
  }, [speak, language])

  // ---------- Action: Listen Again ----------
  const handleListenAgain = useCallback(async () => {
    if (screen.name === "home") {
      // On the home screen, re-play the full welcome intro.
      await playWelcome()
      return
    }
    if (!bannerMessage) {
      const msg =
        language === "hi-IN"
          ? "अभी कहने के लिए कुछ नया नहीं है।"
          : "There is nothing new to say right now."
      setBannerMessage(msg)
      await speak(msg)
      return
    }
    await speak(bannerMessage)
  }, [screen, bannerMessage, speak, language, playWelcome])

  // ---------- Autoplay retry: user taps to enable welcome audio ----------
  const handleWelcomeRetry = useCallback(async () => {
    // Any touch/click interaction is enough to unlock browser autoplay.
    // Try the welcome intro — this call now has a user gesture context.
    await playWelcome()
  }, [playWelcome])

  // ---------- File input change → preview then prompt ----------
  const onFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      photo.onFileSelected(e)
    },
    [photo],
  )

  useEffect(() => {
    if (photo.pendingFile && screen.name === "home") {
      setScreen({ name: "photo-preview" })
      const msg = t("tap_photo_to_send", language)
      setBannerMessage(msg)
      speak(msg)
    }
  }, [photo.pendingFile, screen.name, speak, language])

  // ---------- Render ----------
  return (
    <div className={`app${screen.name === "officer" ? " officer-mode" : ""}`}>
      <header className="app-header">
        <div className="app-title">
          <span className="leaf" aria-hidden="true">🌿</span>
          <span>{t("app_title", language)}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="demo-badge">{t("demo_badge", language)}</span>
          <LanguagePicker
            current={language}
            onChange={(l) => {
              setLanguage(l)
              voice.controller.setLanguage(l)
            }}
          />
          <button
            className="small-btn"
            onClick={() => setScreen({ name: "officer" })}
            type="button"
            title="Officer dashboard"
          >
            🛡️ Officer
          </button>
        </div>
      </header>

      <VoiceBanner
        status={voice.status}
        interim={voice.interim}
        message={bannerMessage}
        autoplayRetry={
          greetingAutoplayBlocked ? (
            <button
              className="autoplay-retry-btn"
              onClick={handleWelcomeRetry}
              type="button"
              aria-label={t("welcome_autoplay_prompt", language)}
            >
              {t("welcome_autoplay_prompt", language)}
            </button>
          ) : undefined
        }
      />

      {voice.error && (
        <div className="error">
          {t("voice_unavailable_title", language)}: {voice.error}
        </div>
      )}

      {screen.name === "home" && (
        <div className="actions">
          <ActionButton
            color="green"
            icon="📸"
            label={t("action_take_photo", language)}
            sublabel={t("action_take_photo_sub", language)}
            onClick={handleTakePhoto}
          />
          <ActionButton
            color="blue"
            icon="❓"
            label={t("action_what_to_do", language)}
            sublabel={t("action_what_to_do_sub", language)}
            onClick={handleWhatToDo}
            disabled={!voice.controller.isRecognitionSupported()}
          />
          <ActionButton
            color="orange"
            icon="⚠️"
            label={t("action_nearby_risk", language)}
            sublabel={t("action_nearby_risk_sub", language)}
            onClick={handleNearbyRisk}
          />
          <ActionButton
            color="red"
            icon="🆘"
            label={t("action_expert_help", language)}
            sublabel={t("action_expert_help_sub", language)}
            onClick={handleExpertHelp}
          />
          <ActionButton
            color="green"
            icon="🌱"
            label={t("action_check_crop", language)}
            sublabel={t("action_check_crop_sub", language)}
            onClick={handleCheckCrop}
          />
          <ActionButton
            color="purple"
            icon="🔊"
            label={t("action_listen_again", language)}
            sublabel={t("action_listen_again_sub", language)}
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
              label={t("action_send_for_analysis", language)}
              sublabel={t("action_send_for_analysis_sub", language)}
              onClick={handlePredict}
            />
            <ActionButton
              color="ghost"
              icon="📷"
              label={t("action_retake_photo", language)}
              onClick={() => {
                photo.reset()
                setScreen({ name: "home" })
              }}
            />
            <ActionButton
              color="blue"
              icon="❓"
              label={t("action_what_to_do", language)}
              sublabel={t("action_what_to_do_sub", language)}
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
            <div>{t("thinking_about_photo", language)}</div>
          </div>
        </div>
      )}

      {screen.name === "result" && (
        <>
          <ResultCard
            prediction={screen.data.prediction}
            language={language}
            onSpeakAgain={handleSpeakResultAgain}
            onDone={handleResultDone}
          />
          {screen.data.risk_forecast && (
            <EarlyWarningCard
              forecast={screen.data.risk_forecast}
              language={language}
            />
          )}
          {(screen.data.prediction.uncertainty_flag ||
            (screen.data.risk_forecast &&
              (screen.data.risk_forecast.risk_level === "high" ||
                screen.data.risk_forecast.risk_level === "critical"))) && (
            <ActionButton
              color="red"
              icon="🆘"
              label={t("action_expert_help", language)}
              sublabel={t("expert_help_recommended", language)}
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
          language={language}
          onDone={() => setScreen({ name: "home" })}
          onSpeak={async () => {
            if (screen.reports.length === 0) {
              await speak(t("no_outbreaks", language))
              return
            }
            const lines = screen.reports
              .slice(0, 3)
              .map((r) => {
                const riskLabel = RISK_LABEL[r.risk_level || "medium"]
                if (language === "hi-IN") {
                  return `${r.disease_type || "एक रोग"} ${r.district || "आपके क्षेत्र"} में, ${riskLabel}, ${r.affected_farms} खेत प्रभावित।`
                }
                return `${r.disease_type || "a disease"} in ${r.district || "your area"}, ${riskLabel}, ${r.affected_farms} farms affected.`
              })
              .join(" ")
            setBannerMessage(lines)
            await speak(lines)
          }}
        />
      )}

      {screen.name === "expert" && (
        <ExpertCard
          language={language}
          onDone={() => setScreen({ name: "home" })}
          onSpeak={async () => {
            const msg =
              language === "hi-IN"
                ? "1800-103-AGRI पर कॉल करें। यह कृषि विज्ञान केंद्र हेल्पलाइन है, मुफ़्त, रोज़ सुबह 6 बजे से रात 10 बजे तक।"
                : "Call 1800-103-AGRI. It is the Krishi Vigyan Kendra helpline, free, every day from six AM to ten PM."
            setBannerMessage(msg)
            await speak(msg)
          }}
        />
      )}

      {screen.name === "officer" && (
        <OfficerDashboard
          onExit={() => setScreen({ name: "home" })}
          onExpertReview={() => setScreen({ name: "expert-review" })}
        />
      )}

      {screen.name === "expert-review" && (
        <ExpertReviewQueue
          onExit={() => setScreen({ name: "officer" })}
        />
      )}

      {screen.name === "follow-up" && (
        <FollowUpCard
          language={language}
          onDone={() => setScreen({ name: "home" })}
          onSpeak={async (text: string) => {
            setBannerMessage(text)
            await speak(text)
          }}
        />
      )}

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
        <div>{t("footer_brand", language)}</div>
        <div>{t("footer_tagline", language)}</div>
        <div style={{ marginTop: 6 }}>{t("footer_demo", language)}</div>
      </footer>
    </div>
  )
}

const RISK_LABEL: Record<string, { en: string; hi: string }> = {
  low: { en: "low risk", hi: "कम जोखिम" },
  medium: { en: "moderate risk", hi: "मध्यम जोखिम" },
  high: { en: "high risk", hi: "उच्च जोखिम" },
  critical: { en: "critical", hi: "गंभीर" },
}

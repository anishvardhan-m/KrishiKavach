// Centralized UI strings — avoid hard-coding any language in components.
// All visible strings MUST go through `t(key, lang)`.

import type { VoiceLanguage } from "../services/voice"

type StringKey =
  | "app_title"
  | "demo_badge"
  | "footer_brand"
  | "footer_tagline"
  | "footer_demo"
  | "greeting_initial"
  | "ready"
  | "tap_photo_to_send"
  | "voice_prompt_please_speak"
  | "action_take_photo"
  | "action_take_photo_sub"
  | "action_what_to_do"
  | "action_what_to_do_sub"
  | "action_nearby_risk"
  | "action_nearby_risk_sub"
  | "action_expert_help"
  | "action_expert_help_sub"
  | "action_listen_again"
  | "action_listen_again_sub"
  | "action_send_for_analysis"
  | "action_send_for_analysis_sub"
  | "action_retake_photo"
  | "not_fully_sure"
  | "expert_help_recommended"
  | "thinking_about_photo"
  | "loading_photo"
  | "loading_outbreaks"
  | "no_outbreaks"
  | "no_outbreaks_explainer"
  | "result_uncertain_warning"
  | "confidence_label"
  | "krishi_vigyan_kendra"
  | "helpline_number"
  | "helpline_hours"
  | "expert_photo_explainer"
  | "voice_mic_unavailable"
  | "voice_omniroute_active"
  | "voice_browser_active"
  | "voice_no_provider"
  | "voice_unavailable_title"
  | "voice_unavailable_explainer"
  | "language_label"
  | "kb_voice_provider"
  | "risk_your_area"
  | "risk_low"
  | "risk_medium"
  | "risk_high"
  | "risk_critical"
  | "risk_expert_help"
  | "risk_expert_help_sub"
  | "risk_act_now"
  | "action_check_crop"
  | "action_check_crop_sub"
  | "follow_up_title"
  | "follow_up_loading"
  | "follow_up_none"
  | "follow_up_none_body"
  | "follow_up_select"
  | "follow_up_case_label"
  | "follow_up_case_improved"
  | "follow_up_case_not_improved"
  | "follow_up_case_expert"
  | "follow_up_notes_placeholder"
  | "follow_up_submit"
  | "follow_up_success_improved"
  | "follow_up_success_not_improved"
  | "follow_up_success_expert"
  | "follow_up_error"
  | "follow_up_confirm_title"
  | "follow_up_confirm_body"
  | "follow_up_back"
  | "welcome_voice_intro"
  | "welcome_autoplay_prompt"

const STRINGS: Record<VoiceLanguage, Partial<Record<StringKey, string>>> = {
  "hi-IN": {
    app_title: "कृषिकवच",
    demo_badge: "SIH डेमो",
    footer_brand: "कृषिकवच — SIH26131",
    footer_tagline:
      "महाराष्ट्र के किसानों के लिए आवाज-आधारित फसल-स्वास्थ्य सहायक",
    footer_demo: "भविष्यवाणी डेमो नियम-आधारित सेवा का उपयोग करती है (स्पष्ट रूप से डेमो चिह्नित)।",
    greeting_initial:
      "नमस्ते! मैं कृषिकवच हूँ। हरा बटन दबाकर अपनी फसल की फोटो लें। मैं बताऊँगा कि क्या समस्या है और क्या करना है।",
    ready: "तैयार",
    tap_photo_to_send: "मैंने फोटो देख ली। नीचे हरा बटन दबाकर भेजें।",
    voice_prompt_please_speak: "कृपया बोलिए। मैं सुन रहा हूँ।",
    action_take_photo: "फोटो लें",
    action_take_photo_sub: "अपनी फसल की फोटो खींचें",
    action_what_to_do: "मुझे क्या करना चाहिए?",
    action_what_to_do_sub: "बोलकर पूछें",
    action_nearby_risk: "आस-पास का खतरा",
    action_nearby_risk_sub: "आपके क्षेत्र की बीमारी सूचनाएँ",
    action_expert_help: "विशेषज्ञ सहायता",
    action_expert_help_sub: "कृषि विशेषज्ञ से बात करें",
    action_listen_again: "फिर से सुनें",
    action_listen_again_sub: "पिछला संदेश दोहराएँ",
    action_send_for_analysis: "जाँच के लिए भेजें",
    action_send_for_analysis_sub: "पता लगाएँ कि क्या समस्या है",
    action_retake_photo: "फोटो फिर लें",
    not_fully_sure: "पूरी तरह निश्चित नहीं",
    expert_help_recommended: "क्योंकि हम पूरी तरह निश्चित नहीं हैं",
    thinking_about_photo: "आपकी फोटो देखी जा रही है...",
    loading_photo: "फोटो देखी जा रही है...",
    loading_outbreaks: "आस-पास की बीमारी सूचनाएँ खोजी जा रही हैं...",
    no_outbreaks: "अभी आपके क्षेत्र में कोई सक्रिय बीमारी नहीं है।",
    no_outbreaks_explainer:
      "अभी आपके क्षेत्र में कोई सक्रिय बीमारी नहीं है। अपनी फसल की नियमित जाँच करते रहें।",
    result_uncertain_warning:
      "हमें पूरी तरह यकीन नहीं है। अगर समस्या बढ़े तो कृपया विशेषज्ञ को बुलाएँ।",
    confidence_label: "विश्वास",
    krishi_vigyan_kendra: "📞 कृषि विज्ञान केंद्र हेल्पलाइन",
    helpline_number: "1800-103-AGRI",
    helpline_hours: "टोल-फ्री, रोज़ सुबह 6 बजे से रात 10 बजे तक",
    expert_photo_explainer:
      "जब आप कॉल करें, कृपया वही फोटो साझा करें जो आपने अभी ली है। विशेषज्ञ वही तस्वीर देखकर बेहतर सलाह दे पाएँगे।",
    voice_mic_unavailable: "इस उपकरण पर माइक्रोफ़ोन उपलब्ध नहीं है — आवाज़ बंद है।",
    voice_omniroute_active: "OmniRoute आवाज़",
    voice_browser_active: "ब्राउज़र आवाज़",
    voice_no_provider: "आवाज़ उपलब्ध नहीं",
    voice_unavailable_title: "आवाज़ उपलब्ध नहीं है",
    voice_unavailable_explainer:
      "माइक्रोफ़ोन या ब्राउज़र आवाज़ उपलब्ध नहीं है। कृपया बटन से आगे बढ़ें।",
    language_label: "भाषा",
    kb_voice_provider: "OmniRoute",
    risk_your_area: "⚠️ आपके क्षेत्र में जोखिम",
    risk_low: "कम जोखिम",
    risk_medium: "मध्यम जोखिम",
    risk_high: "उच्च जोखिम",
    risk_critical: "गंभीर",
    risk_expert_help: "🆘 विशेषज्ञ से संपर्क करें",
    risk_expert_help_sub: "1800-103-AGRI पर कॉल करें",
    risk_act_now: "अभी करें:",
    action_check_crop: "फसल कैसी है?",
    action_check_crop_sub: "सिफ़ारिश के बाद का हाल बताएँ",
    follow_up_title: "फसल का हाल बताएँ",
    follow_up_loading: "रिकॉर्ड देखे जा रहे हैं...",
    follow_up_none: "अभी कुछ नहीं है।",
    follow_up_none_body: "इस समय कोई सिफ़ारिश फॉलो-अप के लिए बाकी नहीं है।",
    follow_up_select: "यह सिफ़ारिश आपकी कौन सी है?",
    follow_up_case_label: "केस",
    follow_up_case_improved: "फसल सुधर गई ✓",
    follow_up_case_not_improved: "फसल नहीं सुधरी",
    follow_up_case_expert: "मुझे विशेषज्ञ चाहिए 🆘",
    follow_up_notes_placeholder: "कुछ और बताना हो तो लिखें (वैकल्पिक)",
    follow_up_submit: "हाल भेजें",
    follow_up_success_improved: "बहुत अच्छा! यह दर्ज हो गया।",
    follow_up_success_not_improved: "ठीक है। हम एक हफ़्ते बाद फिर पूछेंगे।",
    follow_up_success_expert: "ठीक है। हम विशेषज्ञ को बुला रहे हैं।",
    follow_up_error: "माफ़ कीजिए, हाल दर्ज नहीं हो सका।",
    follow_up_confirm_title: "क्या आपने सलाह आज़माई?",
    follow_up_confirm_body: "क्या आपने वह सिफ़ारिश आज़माई जो हमने पिछली बार दी थी?",
    follow_up_back: "वापस जाएँ",
    welcome_voice_intro:
      "नमस्ते! मैं कृषिकवच हूँ। आपकी फसल की सेहत जांचने में मैं आपकी मदद करूंगा। हरे बटन से अपनी फसल की फोटो लें। नीले बटन से पूछें कि आपको क्या करना चाहिए। नारंगी बटन से अपने आसपास की बीमारी का खतरा देखें। लाल बटन से कृषि विशेषज्ञ की मदद लें। और बैंगनी बटन दबाकर जानकारी दोबारा सुन सकते हैं।",
    welcome_autoplay_prompt: "🔊 आवाज़ सुनने के लिए यहाँ दबाएँ",
  },
  "en-IN": {
    app_title: "KrishiKavach",
    demo_badge: "SIH DEMO",
    footer_brand: "KrishiKavach — SIH26131",
    footer_tagline:
      "Voice-first crop-health assistant for Maharashtra farmers",
    footer_demo:
      "Predictions use the demo rule-based service (clearly marked DEMO).",
    greeting_initial:
      "Welcome to KrishiKavach. I am your farming assistant. Tap the green button to take a photo of your crop. I will tell you what is wrong and what to do.",
    ready: "Ready",
    tap_photo_to_send:
      "I see the photo. Tap the green button at the bottom to send it for analysis.",
    voice_prompt_please_speak: "Please speak. I am listening.",
    action_take_photo: "Take Photo",
    action_take_photo_sub: "Photo of your sick crop",
    action_what_to_do: "What should I do?",
    action_what_to_do_sub: "Ask by speaking",
    action_nearby_risk: "Nearby Risk",
    action_nearby_risk_sub: "Disease alerts in your area",
    action_expert_help: "Expert Help",
    action_expert_help_sub: "Call an agriculture expert",
    action_listen_again: "Listen Again",
    action_listen_again_sub: "Repeat the last message",
    action_send_for_analysis: "Send for Analysis",
    action_send_for_analysis_sub: "Find out what is wrong",
    action_retake_photo: "Retake Photo",
    not_fully_sure: "Not fully sure",
    expert_help_recommended: "Because we are not fully sure",
    thinking_about_photo: "Looking at your photo...",
    loading_photo: "Looking at the photo. Please wait.",
    loading_outbreaks: "Looking for nearby disease alerts...",
    no_outbreaks: "No outbreaks reported in your area right now.",
    no_outbreaks_explainer:
      "No active disease outbreaks have been reported in your area right now. Keep checking your crop regularly.",
    result_uncertain_warning:
      "We are not fully sure about this. Please call an expert if the problem gets worse.",
    confidence_label: "Confidence",
    krishi_vigyan_kendra: "📞 Krishi Vigyan Kendra helpline",
    helpline_number: "1800-103-AGRI",
    helpline_hours: "Toll-free, every day from 6 AM to 10 PM",
    expert_photo_explainer:
      "When you call, please share the same photo you just took. The expert will see the same image and can give better advice.",
    voice_mic_unavailable:
      "Microphone not available on this device — voice input disabled.",
    voice_omniroute_active: "OmniRoute voice",
    voice_browser_active: "Browser voice",
    voice_no_provider: "Voice not available",
    voice_unavailable_title: "Voice is not available",
    voice_unavailable_explainer:
      "Microphone or browser voice is not available. Please continue using the buttons.",
    language_label: "Language",
    kb_voice_provider: "OmniRoute",
    risk_your_area: "⚠️ Risk in your area",
    risk_low: "Low risk",
    risk_medium: "Moderate risk",
    risk_high: "High risk",
    risk_critical: "Critical",
    risk_expert_help: "🆘 Call an expert",
    risk_expert_help_sub: "Call 1800-103-AGRI",
    risk_act_now: "Do this now:",
    action_check_crop: "How is my crop?",
    action_check_crop_sub: "Report the result of the advice",
    follow_up_title: "Crop Follow-up",
    follow_up_loading: "Checking your records...",
    follow_up_none: "Nothing due right now.",
    follow_up_none_body: "No follow-ups are due at this time.",
    follow_up_select: "Which recommendation is this about?",
    follow_up_case_label: "Case",
    follow_up_case_improved: "Crop improved ✓",
    follow_up_case_not_improved: "Crop did not improve",
    follow_up_case_expert: "I need an expert 🆘",
    follow_up_notes_placeholder: "Anything else to add? (optional)",
    follow_up_submit: "Send update",
    follow_up_success_improved: "Great! Your update has been recorded.",
    follow_up_success_not_improved: "Noted. We will check again in a week.",
    follow_up_success_expert: "Understood. An expert will be notified.",
    follow_up_error: "Sorry, we could not save your update.",
    follow_up_confirm_title: "Did you try the advice?",
    follow_up_confirm_body: "Did you try what we recommended last time?",
    follow_up_back: "Go back",
    welcome_voice_intro:
      "Welcome to KrishiKavach. I will help you check the health of your crop. Tap the green button to take a photo of your crop. Tap the blue button to ask what you should do. Tap the orange button to see the disease risk around you. Tap the red button to get help from an agriculture expert. Tap the purple button to hear this information again.",
    welcome_autoplay_prompt: "🔊 Tap here to hear the message",
  },
  "mr-IN": {
    app_title: "कृषिकवच",
    demo_badge: "SIH डेमो",
    footer_brand: "कृषिकवच — SIH26131",
    footer_tagline: "महाराष्ट्रातील शेतकऱ्यांसाठी आवाज-आधारित पीक-आरोग्य सहाय्यक",
    footer_demo: "अंदाज डेमो नियम-आधारित सेवा वापरतो (स्पष्टपणे डेमो म्हणून चिन्हांकित).",
    greeting_initial:
      "नमस्कार! मी कृषिकवच आहे. हिरवा बटण दाबून तुमच्या पिकाचा फोटो घ्या. मी सांगतो काय समस्या आहे आणि काय करायचे.",
    ready: "तयार",
    tap_photo_to_send: "मला फोटो दिसला. खालील हिरवा बटण दाबून पाठवा.",
    voice_prompt_please_speak: "कृपया बोला. मी ऐकत आहे.",
    action_take_photo: "फोटो काढा",
    action_take_photo_sub: "तुमच्या पिकाचा फोटो",
    action_what_to_do: "मी काय करावे?",
    action_what_to_do_sub: "बोलून विचारा",
    action_nearby_risk: "जवळपासचा धोका",
    action_nearby_risk_sub: "तुमच्या भागातील रोग सूचना",
    action_expert_help: "तज्ञ मदत",
    action_expert_help_sub: "कृषी तज्ञाशी बोला",
    action_listen_again: "पुन्हा ऐका",
    action_listen_again_sub: "शेवटचा संदेश पुन्हा ऐका",
    action_send_for_analysis: "तपासणीसाठी पाठवा",
    action_send_for_analysis_sub: "काय चुकले ते शोधा",
    action_retake_photo: "फोटो पुन्हा काढा",
    not_fully_sure: "पूर्णपणे खात्री नाही",
    expert_help_recommended: "कारण आम्हाला पूर्ण खात्री नाही",
    thinking_about_photo: "तुमचा फोटो पाहत आहे...",
    loading_photo: "फोटो पाहत आहे. कृपया थांबा.",
    loading_outbreaks: "जवळच्या रोग सूचना शोधत आहे...",
    no_outbreaks: "सध्या तुमच्या भागात कोणताही रोग नाही.",
    no_outbreaks_explainer:
      "सध्या तुमच्या भागात कोणताही सक्रिय रोग नाही. पीक नियमित तपासत रहा.",
    result_uncertain_warning:
      "आम्हाला पूर्ण खात्री नाही. समस्या वाढल्यास कृपया तज्ञांना बोलवा.",
    confidence_label: "विश्वास",
    krishi_vigyan_kendra: "📞 कृषी विज्ञान केंद्र हेल्पलाइन",
    helpline_number: "1800-103-AGRI",
    helpline_hours: "विनामूल्य, रोज सकाळी 6 ते रात्री 10",
    expert_photo_explainer:
      "कॉल करताना कृपया तोच फोटो शेअर करा जो तुम्ही घेतला आहे. तज्ञ तीच प्रतिमा पाहून चांगला सल्ला देतील.",
    voice_mic_unavailable: "या उपकरणावर माइक उपलब्ध नाही — आवाज बंद.",
    voice_omniroute_active: "OmniRoute आवाज",
    voice_browser_active: "ब्राउझर आवाज",
    voice_no_provider: "आवाज उपलब्ध नाही",
    voice_unavailable_title: "आवाज उपलब्ध नाही",
    voice_unavailable_explainer:
      "माइक किंवा ब्राउझर आवाज उपलब्ध नाही. कृपया बटणे वापरा.",
    language_label: "भाषा",
    kb_voice_provider: "OmniRoute",
    risk_your_area: "⚠️ तुमच्या भागातील धोका",
    risk_low: "कमी धोका",
    risk_medium: "मध्यम धोका",
    risk_high: "जास्त धोका",
    risk_critical: "गंभीर",
    risk_expert_help: "🆘 तज्ञांना कॉल करा",
    risk_expert_help_sub: "1800-103-AGRI वर कॉल करा",
    risk_act_now: "आता करा:",
    action_check_crop: "पीक कसे आहे?",
    action_check_crop_sub: "शिफारशीनंतरचा निकाल सांगा",
    follow_up_title: "पीक अपडेट",
    follow_up_loading: "तुमचे रेकॉर्ड पाहत आहे...",
    follow_up_none: "आता काही नाही.",
    follow_up_none_body: "या वेळी कोणतीही फॉलो-अप बाकी नाही.",
    follow_up_select: "ही कोणती शिफारस आहे?",
    follow_up_case_label: "केस",
    follow_up_case_improved: "पीक सुधारले ✓",
    follow_up_case_not_improved: "पीक सुधारले नाही",
    follow_up_case_expert: "मला तज्ञ हवा आहे 🆘",
    follow_up_notes_placeholder: "काही सांगायचे असल्यास लिहा (पर्यायी)",
    follow_up_submit: "अपडेट पाठवा",
    follow_up_success_improved: "छान! तुमचा अपडेट नोंदवला.",
    follow_up_success_not_improved: "ठीक. आम्ही आठवड्याने पुन्हा विचारू.",
    follow_up_success_expert: "समजले. आम्ही तज्ञांना कळवू.",
    follow_up_error: "क्षमस्व, अपडेट जतन करता आला नाही.",
    follow_up_confirm_title: "तुम्ही सल्ला वापरला का?",
    follow_up_confirm_body: "तुम्ही मागे दिलेला सल्ला वापरला का?",
    follow_up_back: "मागे जा",
    welcome_voice_intro:
      "नमस्कार! मी कृषिकवच आहे. मी तुमच्या पिकाच्या आरोग्याची तपासणी करण्यास मदत करतो. हिरव्या बटणाने तुमच्या पिकाचा फोटो काढा. निळ्या बटणाने विचारा की काय करायला पाहिजे. नारंगी बटणाने तुमच्या भागातील रोगाचा धोका पहा. लाल बटणाने कृषी तज्ञांची मदत घ्या. आणि जांभळे बटण दाबून माहिती पुन्हा ऐका.",
    welcome_autoplay_prompt: "🔊 आवाज ऐकण्यासाठी इथे दाबा",
  },
}

export function t(key: StringKey, lang: VoiceLanguage): string {
  return STRINGS[lang]?.[key] ?? STRINGS["en-IN"][key] ?? key
}

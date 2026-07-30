#!/bin/bash
# Generate voiceover audio files using Edge TTS
# Voice: en-US-AndrewMultilingualNeural (Warm, Confident)

VOICE="en-US-AndrewMultilingualNeural"
RATE="-5%"
OUT="public/voiceover"

echo "Generating voiceover files..."

# Scene 1: Logo Intro
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "Introducing DataLake Orchestrator, by ZionAi." \
  --write-media "$OUT/scene1-logo.mp3" 2>/dev/null
echo "✓ Scene 1: Logo"

# Scene 2a: Problem - part 1
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "Every team faces this. A new developer joins and asks, how does the database work?" \
  --write-media "$OUT/scene2a-problem.mp3" 2>/dev/null
echo "✓ Scene 2a: Problem intro"

# Scene 2b: Problem - part 2
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "Nobody has documentation. Days are wasted guessing. And the cycle repeats with every new hire." \
  --write-media "$OUT/scene2b-problem.mp3" 2>/dev/null
echo "✓ Scene 2b: Problem cycle"

# Scene 2c: Problem - solution
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "What if understanding any database took just 30 seconds?" \
  --write-media "$OUT/scene2c-problem.mp3" 2>/dev/null
echo "✓ Scene 2c: Problem solution"

# Scene 3a: Connect
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "Connect to any cloud. Azure, Google Cloud, AWS, or on-premises databases." \
  --write-media "$OUT/scene3a-connect.mp3" 2>/dev/null
echo "✓ Scene 3a: Connect clouds"

# Scene 3b: Connect
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "Each data source connects in seconds, with full schema extraction." \
  --write-media "$OUT/scene3b-connect.mp3" 2>/dev/null
echo "✓ Scene 3b: Connect extraction"

# Scene 4a: Visualize
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "Instantly see your entire schema. Tables, columns, and relationships, all in one view." \
  --write-media "$OUT/scene4a-visualize.mp3" 2>/dev/null
echo "✓ Scene 4a: Visualize schema"

# Scene 4b: Visualize
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "Connect multiple clouds and see unified cross-database relationships." \
  --write-media "$OUT/scene4b-visualize.mp3" 2>/dev/null
echo "✓ Scene 4b: Visualize cross-cloud"

# Scene 4c: Visualize
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "Each data source is color coded, so you always know where your data lives." \
  --write-media "$OUT/scene4c-visualize.mp3" 2>/dev/null
echo "✓ Scene 4c: Visualize colors"

# Scene 4d: Visualize
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "Cross-cloud connections are highlighted automatically. No manual mapping needed." \
  --write-media "$OUT/scene4d-visualize.mp3" 2>/dev/null
echo "✓ Scene 4d: Visualize auto-detect"

# Scene 5a: Chat
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "Ask your database anything in plain English. Our AI explains your schema instantly." \
  --write-media "$OUT/scene5a-chat.mp3" 2>/dev/null
echo "✓ Scene 5a: Chat AI"

# Scene 5b: Chat
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "New to the team? Get answers in seconds, not days." \
  --write-media "$OUT/scene5b-chat.mp3" 2>/dev/null
echo "✓ Scene 5b: Chat onboarding"

# Scene 6: Features
edge-tts --voice "$VOICE" --rate "$RATE" \
  --text "AI auto-documentation, impact analysis, and shareable links. Enterprise features, at a fraction of the cost." \
  --write-media "$OUT/scene6-features.mp3" 2>/dev/null
echo "✓ Scene 6: Features"

echo ""
echo "✅ All voiceover files generated in $OUT/"
ls -la "$OUT/"

# Gmail Auto-Sorter

An automated Gmail classification pipeline that organizes your inbox into custom categories using a hybrid approach: **deterministic rule matching** for known senders/threads and **Gemini 3.6 Flash AI** for intelligent contextual sorting.

---

## 🛠️ System Architecture

The sorter processes emails in a structured multi-tier pipeline to maximize speed and minimize API cost:

1. **Unread Filter:** Skips unread threads to ensure only read/reviewed emails are processed.
2. **Label Inheritance:** If an email is part of an ongoing thread, it automatically inherits the label previously assigned to that thread.
3. **Deterministic Address Matching (`address.json`):** Matches incoming email sender addresses directly to predefined labels (e.g., specific newsletters, department emails).
4. **AI Classification (`google-genai`):** Unresolved emails are batched and classified in a single call using **Gemini 3.6 Flash** guided by detailed criteria in `system_instruction.md`.
5. **Batch Gmail Update:** Applies custom labels and removes threads from `INBOX` via the Gmail API.

---

## 📁 Repository Structure

```text
.
├── email_sorter.py          # Main execution script & pipeline logic
├── export_labels.py         # Helper script to export Gmail labels to labels.json
├── system_instruction.md    # Master instructions & few-shot examples for Gemini (Git ignored)
├── labels.json              # Mapping of Label Names to Gmail Label IDs (Git ignored)
├── address.json             # Hardcoded { sender_address: label_name } overrides (Git ignored)
├── credentials.json         # Google OAuth 2.0 client credentials (Git ignored)
├── token.json               # Generated user authentication token (Git ignored)
└── requirements.txt         # Project dependencies

```

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.10+
- A Google Cloud Project with the **Gmail API** enabled.
- OAuth 2.0 Client ID Credentials saved as `credentials.json` in the project root.
- A Gemini API Key from Google AI Studio.

### 2. Installation & Setup

Clone the repository, create a virtual environment, and install dependencies:

```bash
# Clone the repository
git clone https://github.com/kshitij-D-anand/email-sorter.git
cd email-sorter

# Create and activate a virtual environment
python -m venv venv

# Linux/macOS:
source venv/bin/activate
# Windows (Command Prompt):
# venv\Scripts\activate.bat
# Windows (PowerShell):
# venv\Scripts\Activate.ps1

# Install required packages
pip install -r requirements.txt
```

#### Set up Gemini API Key

Append your API key to your virtual environment's activation script so it loads automatically whenever activated:

```bash
cat << 'EOF' >> venv/bin/activate

# Gemini API Key configuration
export GEMINI_API_KEY="your_actual_gemini_api_key_here"
EOF

# Reload activation script to export key
source venv/bin/activate

```

### 3. Configuration

1. **Gmail Labels (`labels.json`):** Define your category-to-ID mappings:

```json
{
  "Academics": "Label_1",
  "Events and Seminar": "Label_2",
  "Noticeboard": "Label_3"
}
```

Run the label helper script to pull your account's exact Label IDs automatically:

```bash
python export_labels.py
```

2. **Address Rules (`address.json`):** Map known senders directly to avoid unnecessary AI calls:

```json
{
  "no-reply@canvas.edu": "Academics",
  "bulletin@campus.edu": "Noticeboard"
}
```

3. **System Instructions (`system_instruction.md`):** Customize your categorization rules, target labels, and few-shot example emails.

> ⚠️ **CRITICAL:** Do NOT modify the **System Instructions** or **Output Constraint** sections below. The Python parser strictly expects the `#id : LABEL` format. Only edit the **Predefined Labels & Criteria** section to match your personal categories.

```markdown
**System Instructions:**
You are an automated email categorization system. Your task is to classify incoming emails into exactly one of the predefined labels listed below.

Analyze the provided email Subject and Body, match it against the definitions and examples, and determine the single best fit.

**Output Constraint:**
You will be provided with a batch of emails, each starting with a unique ID. You must classify every single email. Respond ONLY with the ID and the exact label name string in this exact format: #id : LABEL. Output each result on a new line. Do not include any formatting, markdown, explanations, or conversational text. If an email does not fit any category, output #id : Uncategorized

<!-- =================================================================
     CUSTOMIZE BELOW THIS LINE: Replace with your own labels & criteria
     ================================================================= -->

**Predefined Labels & Criteria:**

- Academics: Course announcements, grades, assignments, exam schedules.
- Events and Seminar: Guest lectures, workshops, hackathons, club events.
- Noticeboard: Administrative policy updates, campus maintenance, official advisories.
```

---

## ⚡ Usage

Run the sorter manually from the terminal:

```bash
python email_sorter.py

```

On first run, a browser window will open requesting access to your Gmail account (`gmail.modify` scope). Once authenticated, `token.json` will be created for future automated runs.

---

## 🤖 How Gemini Batch Classification Works

Instead of calling the API once per email, emails are chunked into batches (default: 25 emails) and serialized into JSON. Gemini evaluates all items in a single pass and returns classifications using a strict identifier format:

```text
#18f234a9b01 : Academics
#18f234a9b02 : Events and Seminar
#18f234a9b03 : Uncategorized

```

If an email does not match any category defined in `system_instruction.md`, it is assigned `Uncategorized` and left safely in your inbox for manual review.

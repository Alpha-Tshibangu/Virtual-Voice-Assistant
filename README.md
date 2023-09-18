## Virtual Voice Assistant

### Overview

The Virtual Voice Assistant is a system designed to handle over-the-phone voice interactions. Its adaptive and context-aware design allows it to be integrated into numerous applications, ranging from customer support in retail to receptionist duties in medical or corporate environments. In this specific repository, the Virtual Voice Assistant has been tailored for the Chisholm Medical Centre for use as a virtual receptionist. Its primary role here is to assist patients by providing information, handling inquiries, checking availability and booking medical appointments. It can, however, be adapted for various other use cases.

### Features

1. **Voice Call Handling**: Uses the Vonage API to handle incoming calls.
2. **Voice Transcription**: Transcribes voice inputs to text using the Whisper ASR service.
3. **Natural Language Processing**: Utilises OpenAI's GPT-4 Chat Completion API to interpret transcribed text and make decisions.
4. **Semantic Search**: Uses Pinecone for potential semantic searches or other functionalities.
5. **SMS Service**: Uses Vonage SMS to send SMS notifications.

### Key Functionalities

- **Appointment Booking**: Books appointments with specific doctors at the Chisholm Medical Centre.
- **Information Provision**: Provides information about the services, doctors, and available time slots at the centre.
- **Call Forwarding**: Can forward calls to a human receptionist upon request.
- **Guided Responses**: Provides responses suitable for text-to-speech conversion, ensuring clarity for callers.

### Technical Details

- **Language**: Python
- **External Services**:
  - **Vonage**: For handling voice calls and sending SMS.
  - **Whisper ASR**: For voice transcription.
  - **OpenAI GPT-4 Chat Completion API**: For interpreting and processing transcribed texts.
  - **Pinecone**: Used for semantic search.

### Setup

1. Ensure you have access to the APIs mentioned above and their respective keys.
2. Initialise the necessary services with their respective keys:

   - OpenAI API key
   - Vonage API key and private key
   - Pinecone API key

3. Run the script to start the virtual assistant.

### Pinecone: Knowledge-base Retrieval

The system employs Pinecone, a vector store, to serve as its knowledge base. Pinecone assists in storing embeddings and converting textual data (user input queries) for retrieval of similar information from documents. This facilitates quick and context-aware responses by the assistant based on the retreived text. Ensure you have node and npm installed, navigate to the `utils` folder and follow the instructions below.

#### Ingesting Data into Pinecone:

1. **Setup**:

   - Visit [pinecone](https://pinecone.io/) to create and retrieve your API keys. Also, retrieve your environment and index name from the dashboard.
   - Ensure you have set the Pinecone configurations in your `.env` file.
   - Place the desired data or documents you want to ingest into the designated `docs` folder of the project.

2. **Data Conversion**:
   - Run the script `npm run ingest` to 'ingest' and embed your documents.
   - Verify the embeddings and content have been successfully added to Pinecone using the Pinecone dashboard.

Absolutely! Here's the continuation of the README, incorporating the Development, Setup, Troubleshooting sections, and the reference to the tutorial video:

---

### Development and Setup

1. **Repository Setup**:

   - **Clone the Repo**:
     ```
     git clone [github https url]
     ```
   - **Install Required Packages**:
     1. First, install yarn globally if you haven't already:
        ```
        npm install yarn -g
        ```
     2. Then install the necessary packages for the project:
        ```
        yarn install
        ```
     3. After installation, a `node_modules` folder should appear in the project directory.

2. **Environment Configuration**:
   - Copy `.env.example` to a new file named `.env`.
   - Your `.env` file should contain keys and configurations such as:
     ```
     OPENAI_API_KEY=
     PINECONE_API_KEY=
     PINECONE_ENVIRONMENT=
     PINECONE_INDEX_NAME=
     ```
   - Obtain the required API keys from [openai](https://help.openai.com/en/articles/4936850-where-do-i-find-my-secret-api-key) and [pinecone](https://pinecone.io/), and then populate the `.env` file with the appropriate values.
3. **Pinecone Configuration**:

   - In the `config` folder, replace the `PINECONE_NAME_SPACE` value with a namespace of your choice for storing embeddings on Pinecone.

4. **Embedding PDF Data**:
   - Place your desired PDF files or folders containing PDFs in the `docs` directory.
   - Execute `npm run ingest` to process and embed your documents. Ensure there are no errors during this step.
   - Validate that your embeddings and data are present in Pinecone via its dashboard.

For a more detailed walkthrough and visual guide on setting up and using Pinecone, please refer to [this tutorial video](https://www.youtube.com/watch?v=ih9PBGVVOO4).

### Troubleshooting

If you encounter issues during setup or operation, consider the following solutions:

**General Errors**:

- Ensure your Node version is up-to-date by checking with `node -v`.
- Convert problematic PDFs to text or use different PDFs. Some PDFs may be scanned, corrupted, or require OCR for text conversion.
- Verify the versions of Pinecone you're using match this repo's requirements.
- Validate the presence of a correctly configured `.env` file with accurate API keys, environment, and index name.
- Confirm you have sufficient OpenAI credits and a valid billing method.
- Ensure no global environment conflicts with the project's local `.env` values.

**Pinecone-Specific Issues**:

- Check that the `environment` and `index` values in Pinecone's dashboard align with those in `pinecone.ts` and `.env`.
- Ensure the vector dimensions are set to `1536`.
- Pinecone namespaces should be in lowercase.
- For users on Pinecone's Starter (free) plan, indexes are removed after 7 days of inactivity. Regularly send an API request to Pinecone to reset this counter.
- If persistent issues occur with Pinecone, start over with a new project, index, and cloned repo.

const axios = require("axios");

async function run() {
  const response = await axios.post("http://localhost:11434/api/generate", {
    model: "llama3.1:latest",
    prompt:
      "Say Hello, World!. Only respond with the text i mentioned, no other text or formatting.",
    stream: false,
  });

  console.log(response.data.response);
}

run();

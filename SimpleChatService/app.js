require("dotenv").config();

const express = require("express");
const cors = require("cors");

const { ChatOllama } = require("@langchain/ollama");

const app = express();

app.use(cors());
app.use(express.json());

app.get("/", (req, res) => {
  res.json({
    status: "running",
    model: process.env.MODEL,
  });
});

app.post("/chat", async (req, res) => {
  try {
    const { message, systemPrompt, temperature } = req.body;

    if (!message) {
      return res.status(400).json({
        success: false,
        error: "message is required",
      });
    }

    const llm = new ChatOllama({
      model: process.env.MODEL,
      temperature: temperature ?? 0.7,
    });

    const response = await llm.invoke([
      {
        role: "system",
        content: systemPrompt ?? "You are a helpful AI assistant.",
      },
      {
        role: "user",
        content: message,
      },
    ]);

    res.json({
      success: true,
      answer: response.content,
    });
  } catch (error) {
    console.error(error);

    res.status(500).json({
      success: false,
      error: error.message,
    });
  }
});

app.listen(process.env.PORT, () => {
  console.log(`Server running on port ${process.env.PORT}`);
});

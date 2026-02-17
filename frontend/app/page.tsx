"use client";

import { useState } from "react";

export default function Home() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handlePredict = async () => {
    setLoading(true);

    const response = await fetch("http://127.0.0.1:8000/predict", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        video_title:
          "TOXIC Official Trailer | Yash | Geetu Mohandas | KVN Productions",
        video_description:
          "Presenting the official trailer of TOXIC starring Yash.",
        video_tags:
          "toxic trailer,yash toxic,yash new movie,official trailer",
        channel_title: "KVN Productions",
        video_category: "Entertainment",
        country: "IN",
        subs: 2500000,
        views: 850000000,
        vids: 120,
        duration: 152,
      }),
    });

    const data = await response.json();
    setResult(data);
    setLoading(false);
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-black text-white p-6">
      <h1 className="text-4xl font-bold mb-6">
        YouTube Trending Predictor 🚀
      </h1>

      <button
        onClick={handlePredict}
        className="bg-green-500 px-6 py-3 rounded-lg text-black font-semibold hover:bg-green-400"
      >
        {loading ? "Predicting..." : "Predict Trending"}
      </button>

      {result && (
        <div className="mt-8 bg-gray-900 p-6 rounded-lg w-full max-w-lg">
          <p className="text-xl font-bold mb-2">
            Probability: {(result.trending_probability * 100).toFixed(2)}%
          </p>
          <p className="mb-2">Confidence: {result.confidence_bucket}</p>
          <hr className="my-3 border-gray-700" />
          <p>Text Score: {result.model_breakdown.text_score}</p>
          <p>Numeric Score: {result.model_breakdown.numeric_score}</p>
          <p>Psychology Score: {result.model_breakdown.psychology_score}</p>
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";

export default function Dashboard() {
  const [countries, setCountries] = useState([]);
  const [topVideos, setTopVideos] = useState([]);
  const [avgLikes, setAvgLikes] = useState([]);

  useEffect(() => {
    fetch("http://localhost:8000/dashboard/country-count")
      .then(res => res.json())
      .then(data => setCountries(data));

    fetch("http://localhost:8000/dashboard/top-views")
      .then(res => res.json())
      .then(data => setTopVideos(data));

    fetch("http://localhost:8000/dashboard/avg-likes")
      .then(res => res.json())
      .then(data => setAvgLikes(data));
  }, []);

  return (
    <div style={{ padding: "40px" }}>
      <h1>📊 YouTube Trending Dashboard</h1>

      <h2>Country Distribution</h2>
      <pre>{JSON.stringify(countries, null, 2)}</pre>

      <h2>Top 10 Videos</h2>
      <pre>{JSON.stringify(topVideos, null, 2)}</pre>

      <h2>Average Likes</h2>
      <pre>{JSON.stringify(avgLikes, null, 2)}</pre>
    </div>
  );
}

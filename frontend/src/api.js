import axios from 'axios';

const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || '/api',
    withCredentials: true,
    headers: {
        'ngrok-skip-browser-warning': 'true' // <--- ADD THIS LINE
    }
});

export default api;
// API Client Utility Wrapper
const API = {
    async get(endpoint) {
        try {
            const res = await fetch(endpoint);
            if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
            return await res.json();
        } catch (e) {
            console.error(`API GET error on ${endpoint}:`, e);
            throw e;
        }
    },

    async post(endpoint, body) {
        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
            return await res.json();
        } catch (e) {
            console.error(`API POST error on ${endpoint}:`, e);
            throw e;
        }
    },

    async put(endpoint, body) {
        try {
            const res = await fetch(endpoint, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
            return await res.json();
        } catch (e) {
            console.error(`API PUT error on ${endpoint}:`, e);
            throw e;
        }
    },

    async delete(endpoint) {
        try {
            const res = await fetch(endpoint, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
            return await res.json();
        } catch (e) {
            console.error(`API DELETE error on ${endpoint}:`, e);
            throw e;
        }
    }
};

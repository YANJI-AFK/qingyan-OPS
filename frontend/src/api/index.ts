import axios from 'axios'

const api = axios.create({
  baseURL: 'http://127.0.0.1:5000',
  timeout: 10000,
})

export const getTickets = () => api.get('/api/tickets')
export const getTicketsStat = () => api.get('/api/tickets/stat')
export const getServerMetrics = () => api.get('/api/servers/metrics')
export const updateTicket = (id: number, status: string) =>
  api.post('/api/tickets/update', { id, status })

export default api

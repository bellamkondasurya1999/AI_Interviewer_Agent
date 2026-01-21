import { motion } from 'framer-motion'

const BAR_HEIGHTS = [10, 18, 12, 22, 14, 20]

const Visualizer = ({ isActive }) => {
  return (
    <div className="flex h-6 items-end gap-1">
      {BAR_HEIGHTS.map((height, index) => (
        <motion.span
          key={`bar-${index}`}
          className="w-1 rounded-full bg-indigo-300/80"
          animate={
            isActive
              ? { height: [6, height, 8, height - 4] }
              : { height: 6 }
          }
          transition={{
            duration: 0.8,
            repeat: isActive ? Infinity : 0,
            repeatType: 'reverse',
            delay: index * 0.08,
          }}
        />
      ))}
    </div>
  )
}

export default Visualizer

cmake_minimum_required(VERSION 3.0.2)
project(hybrid_video_recorder)

find_package(catkin REQUIRED COMPONENTS
  cv_bridge
  message_generation
  rospy
  sensor_msgs
  std_msgs
  std_srvs
)

catkin_python_setup()

add_service_files(
  FILES
  RecordingControl.srv
)

generate_messages(
  DEPENDENCIES
  std_msgs
)

catkin_package(
  CATKIN_DEPENDS cv_bridge message_runtime rospy sensor_msgs std_msgs std_srvs
)

catkin_install_python(PROGRAMS
  scripts/hybrid_video_worker_node.py
  scripts/hybrid_video_manager_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY config launch
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)
